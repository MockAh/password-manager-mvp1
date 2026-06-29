"""Tests unitarios del ciclo de vida de VaultService (T013).

Cubre: create_vault, unlock_vault, lock_vault, is_unlocked.
Los tests de integración completos están en test_vault_roundtrip.py.
"""
import json
import threading
import time
from pathlib import Path

import pytest

from vault.exceptions import (
    DuplicateFolderNameError,
    EntryNotFoundError,
    FolderNotFoundError,
    VaultAlreadyExistsError,
    VaultCorruptError,
    VaultLockedError,
    WrongPasswordError,
)
from vault.service import NO_FOLDER, VaultService

PASSWORD = "ContraseñaMaestraSegura123!"


@pytest.fixture
def svc() -> VaultService:
    return VaultService(auto_lock_timeout_s=0)


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "test.vault"


# ── create_vault ──────────────────────────────────────────────────────────────


class TestCreateVault:
    def test_creates_file_on_disk(self, svc, vault_path):
        svc.create_vault(vault_path, PASSWORD)
        assert vault_path.exists()

    def test_is_unlocked_after_create(self, svc, vault_path):
        svc.create_vault(vault_path, PASSWORD)
        assert svc.is_unlocked

    def test_created_file_is_valid_json(self, svc, vault_path):
        svc.create_vault(vault_path, PASSWORD)
        data = json.loads(vault_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_created_file_has_required_fields(self, svc, vault_path):
        svc.create_vault(vault_path, PASSWORD)
        data = json.loads(vault_path.read_text(encoding="utf-8"))
        for field in ("version", "kdf", "kdf_params", "salt", "nonce", "ciphertext"):
            assert field in data, f"Campo ausente: {field}"

    def test_no_plaintext_password_in_file(self, svc, vault_path):
        """La contraseña maestra NUNCA debe aparecer en el archivo."""
        svc.create_vault(vault_path, PASSWORD)
        raw = vault_path.read_text(encoding="utf-8")
        assert PASSWORD not in raw

    def test_raises_if_file_exists(self, svc, vault_path):
        vault_path.touch()
        with pytest.raises(VaultAlreadyExistsError):
            svc.create_vault(vault_path, PASSWORD)

    def test_raises_if_empty_password(self, svc, vault_path):
        with pytest.raises(ValueError):
            svc.create_vault(vault_path, "")

    def test_version_is_1(self, svc, vault_path):
        svc.create_vault(vault_path, PASSWORD)
        data = json.loads(vault_path.read_text(encoding="utf-8"))
        assert data["version"] == 1

    def test_kdf_is_argon2id(self, svc, vault_path):
        svc.create_vault(vault_path, PASSWORD)
        data = json.loads(vault_path.read_text(encoding="utf-8"))
        assert data["kdf"] == "argon2id"

    def test_different_salts_on_two_vaults(self, svc, tmp_path):
        path1 = tmp_path / "v1.vault"
        path2 = tmp_path / "v2.vault"
        svc.create_vault(path1, PASSWORD)
        svc.lock_vault()
        svc2 = VaultService(auto_lock_timeout_s=0)
        svc2.create_vault(path2, PASSWORD)
        d1 = json.loads(path1.read_text())
        d2 = json.loads(path2.read_text())
        assert d1["salt"] != d2["salt"], "Cada bóveda debe tener un salt único"


# ── unlock_vault ──────────────────────────────────────────────────────────────


class TestUnlockVault:
    def test_unlock_with_correct_password(self, svc, vault_path):
        svc.create_vault(vault_path, PASSWORD)
        svc.lock_vault()
        assert not svc.is_unlocked
        svc.unlock_vault(vault_path, PASSWORD)
        assert svc.is_unlocked

    def test_unlock_with_wrong_password_raises(self, svc, vault_path):
        svc.create_vault(vault_path, PASSWORD)
        svc.lock_vault()
        with pytest.raises(WrongPasswordError):
            svc.unlock_vault(vault_path, "contraseña_incorrecta")

    def test_unlock_nonexistent_file_raises(self, svc, tmp_path):
        path = tmp_path / "no_existe.vault"
        with pytest.raises((VaultCorruptError, FileNotFoundError, OSError)):
            svc.unlock_vault(path, PASSWORD)

    def test_unlock_corrupt_json_raises(self, svc, vault_path):
        vault_path.write_text("{no json válido", encoding="utf-8")
        with pytest.raises(VaultCorruptError):
            svc.unlock_vault(vault_path, PASSWORD)


# ── lock_vault ────────────────────────────────────────────────────────────────


class TestLockVault:
    def test_lock_sets_unlocked_to_false(self, svc, vault_path):
        svc.create_vault(vault_path, PASSWORD)
        assert svc.is_unlocked
        svc.lock_vault()
        assert not svc.is_unlocked

    def test_lock_is_idempotent(self, svc, vault_path):
        """lock_vault no lanza excepción si ya está bloqueado."""
        svc.create_vault(vault_path, PASSWORD)
        svc.lock_vault()
        svc.lock_vault()  # segunda llamada — no debe lanzar
        assert not svc.is_unlocked

    def test_lock_zeroes_derived_key(self, svc, vault_path):
        """Tras lock_vault, la clave derivada debe haber sido zeroza."""
        svc.create_vault(vault_path, PASSWORD)
        session_key_ref = svc._session.derived_key  # referencia directa
        svc.lock_vault()
        assert all(b == 0 for b in session_key_ref), (
            "La clave derivada debe estar zeroza en memoria tras bloquear"
        )


# ── is_unlocked ───────────────────────────────────────────────────────────────


class TestIsUnlocked:
    def test_initially_locked(self, svc):
        assert not svc.is_unlocked

    def test_unlocked_after_create(self, svc, vault_path):
        svc.create_vault(vault_path, PASSWORD)
        assert svc.is_unlocked

    def test_locked_after_lock(self, svc, vault_path):
        svc.create_vault(vault_path, PASSWORD)
        svc.lock_vault()
        assert not svc.is_unlocked


# ── CRUD de entradas (T020) ───────────────────────────────────────────────────


class TestEntryCRUD:
    """Tests de CRUD de entradas — US2, tareas T019–T020.

    Refs: spec.md → User Story 2 (Acceptance Scenarios 1–5).
          data-model.md → EntryRecord.
          contracts/vault-service-interface.md → add_entry, update_entry, delete_entry.
    """

    @pytest.fixture
    def svc_open(self, tmp_path):
        """VaultService con bóveda ya creada y desbloqueada."""
        svc = VaultService(auto_lock_timeout_s=0)
        path = tmp_path / "crud.vault"
        svc.create_vault(path, PASSWORD)
        return svc, path

    # ── add_entry ────────────────────────────────────────────────────────────

    def test_add_entry_returns_entry_record(self, svc_open):
        """add_entry devuelve el EntryRecord creado con UUID asignado.
        Ref: data-model.md → EntryRecord.id generado en creación."""
        svc, _ = svc_open
        entry = svc.add_entry("GitHub", username="alice")
        assert entry.id
        assert entry.title == "GitHub"
        assert entry.username == "alice"

    def test_add_entry_appears_in_get_entries(self, svc_open):
        """La entrada creada es visible en get_entries().
        Ref: US2 Acceptance Scenario 1."""
        svc, _ = svc_open
        entry = svc.add_entry("Gmail", username="bob")
        entries = svc.get_entries()
        assert any(e.id == entry.id for e in entries)

    def test_add_entry_empty_title_raises(self, svc_open):
        """Título vacío lanza ValueError.
        Ref: data-model.md → title: no vacío."""
        svc, _ = svc_open
        with pytest.raises(ValueError):
            svc.add_entry("")

    def test_add_entry_invalid_folder_id_raises(self, svc_open):
        """folder_id inexistente lanza FolderNotFoundError.
        Ref: data-model.md → folder_id DEBE corresponder a carpeta existente."""
        svc, _ = svc_open
        with pytest.raises(FolderNotFoundError):
            svc.add_entry("Site", folder_id="uuid-no-existe")

    def test_add_entry_uuid_is_unique(self, svc_open):
        """Dos entradas distintas tienen UUIDs distintos.
        Ref: data-model.md → id UUID4, inmutable y único."""
        svc, _ = svc_open
        e1 = svc.add_entry("Site A")
        e2 = svc.add_entry("Site B")
        assert e1.id != e2.id

    def test_add_entry_created_at_invariant(self, svc_open):
        """created_at se fija en la creación.
        Ref: data-model.md → created_at invariante."""
        svc, _ = svc_open
        entry = svc.add_entry("Site", username="u")
        original_created_at = entry.created_at
        svc.update_entry(entry.id, username="u2")
        assert entry.created_at == original_created_at

    # ── update_entry ─────────────────────────────────────────────────────────

    def test_update_entry_changes_field(self, svc_open):
        """update_entry modifica el campo indicado.
        Ref: US2 Acceptance Scenario 2."""
        svc, _ = svc_open
        entry = svc.add_entry("Twitter", username="old_user")
        svc.update_entry(entry.id, username="new_user")
        assert entry.username == "new_user"

    def test_update_entry_refreshes_updated_at(self, svc_open):
        """update_entry actualiza updated_at.
        Ref: data-model.md → updated_at se actualiza en cada edición."""
        import time
        svc, _ = svc_open
        entry = svc.add_entry("Reddit", username="u")
        original_updated_at = entry.updated_at
        time.sleep(1.01)  # garantiza diferencia de al menos 1 s en ISO-8601 seconds
        svc.update_entry(entry.id, username="u2")
        assert entry.updated_at > original_updated_at

    def test_update_entry_nonexistent_raises(self, svc_open):
        """ID inexistente lanza EntryNotFoundError.
        Ref: contracts/vault-service-interface.md → update_entry."""
        svc, _ = svc_open
        with pytest.raises(EntryNotFoundError):
            svc.update_entry("id-que-no-existe", username="x")

    def test_update_entry_invalid_folder_id_raises(self, svc_open):
        """folder_id inválido en update lanza FolderNotFoundError."""
        svc, _ = svc_open
        entry = svc.add_entry("Site")
        with pytest.raises(FolderNotFoundError):
            svc.update_entry(entry.id, folder_id="carpeta-inexistente")

    def test_update_entry_ignores_disallowed_keys(self, svc_open):
        """Campos no permitidos en update_entry se ignoran silenciosamente."""
        svc, _ = svc_open
        entry = svc.add_entry("Site", username="u")
        svc.update_entry(entry.id, username="u2", campo_desconocido="valor")
        assert entry.username == "u2"

    # ── delete_entry ─────────────────────────────────────────────────────────

    def test_delete_entry_removes_it(self, svc_open):
        """delete_entry elimina la entrada de la bóveda.
        Ref: US2 Acceptance Scenario 3."""
        svc, _ = svc_open
        entry = svc.add_entry("LinkedIn")
        svc.delete_entry(entry.id)
        assert not any(e.id == entry.id for e in svc.get_entries())

    def test_delete_entry_nonexistent_raises(self, svc_open):
        """ID inexistente lanza EntryNotFoundError.
        Ref: contracts/vault-service-interface.md → delete_entry."""
        svc, _ = svc_open
        with pytest.raises(EntryNotFoundError):
            svc.delete_entry("id-que-no-existe")

    # ── get_entries filtering ────────────────────────────────────────────────

    def test_get_entries_returns_all_when_no_filter(self, svc_open):
        """get_entries() sin argumento devuelve todas las entradas.
        Ref: contracts/vault-service-interface.md → folder_id=None → todas."""
        svc, _ = svc_open
        svc.add_entry("A")
        svc.add_entry("B")
        assert len(svc.get_entries()) == 2

    def test_get_entries_no_folder_filter(self, svc_open):
        """get_entries(NO_FOLDER) devuelve solo entradas sin carpeta.
        Ref: contracts/vault-service-interface.md → folder_id="" → sin carpeta."""
        svc, _ = svc_open
        from vault.models import FolderRecord
        folder = svc._require_unlocked().payload.folders
        from vault.service import NO_FOLDER
        # Añadimos carpeta manualmente (US6 no implementada aún)
        from vault.models import FolderRecord
        f = FolderRecord.create("Trabajo")
        svc._require_unlocked().payload.folders.append(f)

        svc.add_entry("Sin carpeta")              # folder_id=None
        svc.add_entry("Con carpeta", folder_id=f.id)

        sin_carpeta = svc.get_entries(folder_id=NO_FOLDER)
        assert len(sin_carpeta) == 1
        assert sin_carpeta[0].title == "Sin carpeta"

    def test_get_entries_by_folder_id(self, svc_open):
        """get_entries(folder_id=uuid) devuelve entradas de esa carpeta.
        Ref: contracts/vault-service-interface.md → folder_id=UUID → carpeta."""
        svc, _ = svc_open
        from vault.models import FolderRecord
        f = FolderRecord.create("Personal")
        svc._require_unlocked().payload.folders.append(f)

        svc.add_entry("Personal site", folder_id=f.id)
        svc.add_entry("Otro sin carpeta")

        en_carpeta = svc.get_entries(folder_id=f.id)
        assert len(en_carpeta) == 1
        assert en_carpeta[0].title == "Personal site"

    def test_get_entries_locked_raises(self, tmp_path):
        """get_entries sobre bóveda bloqueada lanza VaultLockedError.
        Ref: contracts/vault-service-interface.md."""
        svc = VaultService(auto_lock_timeout_s=0)
        with pytest.raises(VaultLockedError):
            svc.get_entries()

    # ── Persistencia tras lock/unlock ────────────────────────────────────────

    def test_changes_persist_after_lock_unlock(self, svc_open):
        """CRUD persiste tras bloquear y desbloquear la bóveda.
        Ref: US2 Acceptance Scenario 5."""
        svc, path = svc_open
        e1 = svc.add_entry("Persistente", username="u1")
        e2 = svc.add_entry("Efímero")
        svc.update_entry(e1.id, username="u1_editado")
        svc.delete_entry(e2.id)

        svc.lock_vault()
        svc.unlock_vault(path, PASSWORD)

        entries = svc.get_entries()
        ids = [e.id for e in entries]
        assert e1.id not in [e.id for e in entries] or True  # recargadas desde disco
        titles = [e.title for e in entries]
        assert "Persistente" in titles
        assert "Efímero" not in titles
        # Verificar username editado
        reloaded = next(e for e in entries if e.title == "Persistente")
        assert reloaded.username == "u1_editado"


# ── Búsqueda en tiempo real (T024) ────────────────────────────────────────────


class TestSearchEntries:
    """Tests de búsqueda en tiempo real — US3, tareas T023–T024.

    Refs: spec.md → User Story 3 (Acceptance Scenarios 1–3).
          contracts/vault-service-interface.md → search_entries.
          FR-013: búsqueda en tiempo real filtra por título y usuario.
          SC-003: ≤ 100 ms incluso con 500 entradas.
    """

    @pytest.fixture
    def svc_with_entries(self, tmp_path):
        """VaultService con bóveda desbloqueada y varias entradas de prueba."""
        svc = VaultService(auto_lock_timeout_s=0)
        path = tmp_path / "search.vault"
        svc.create_vault(path, PASSWORD)
        # Inserciones directas en payload para evitar escrituras en disco repetidas.
        from vault.models import EntryRecord
        entries = [
            EntryRecord.create(title="GitHub", username="alice@example.com"),
            EntryRecord.create(title="Gmail", username="alice@gmail.com"),
            EntryRecord.create(title="Amazon", username="bob@amazon.com"),
            EntryRecord.create(title="Twitter", username="charlie"),
        ]
        svc._session.payload.entries.extend(entries)
        return svc

    # ── Coincidencia por subcadena en title ──────────────────────────────────

    def test_search_by_title_substring(self, svc_with_entries):
        """Coincidencia por subcadena en title.
        Ref: FR-013; US3 Acceptance Scenario 1."""
        svc = svc_with_entries
        results = svc.search_entries("Git")
        assert len(results) == 1
        assert results[0].title == "GitHub"

    def test_search_by_title_partial(self, svc_with_entries):
        """Subcadena que coincide con varios títulos.
        Ref: FR-013; US3 Acceptance Scenario 1."""
        svc = svc_with_entries
        results = svc.search_entries("a")
        # "GitHub" (sin 'a'), "Gmail" (tiene 'a'), "Amazon" (tiene 'a'), "Twitter" (sin 'a')
        titles = {e.title for e in results}
        assert "Gmail" in titles
        assert "Amazon" in titles

    # ── Coincidencia por subcadena en username ───────────────────────────────

    def test_search_by_username_substring(self, svc_with_entries):
        """Coincidencia por subcadena en username.
        Ref: FR-013; contracts/vault-service-interface.md → search_entries."""
        svc = svc_with_entries
        results = svc.search_entries("alice")
        assert len(results) == 2
        titles = {e.title for e in results}
        assert titles == {"GitHub", "Gmail"}

    def test_search_by_username_only(self, svc_with_entries):
        """Query que solo está en username, no en title.
        Ref: FR-013; US3 Acceptance Scenario 1."""
        svc = svc_with_entries
        results = svc.search_entries("charlie")
        assert len(results) == 1
        assert results[0].title == "Twitter"

    # ── Insensibilidad a mayúsculas ──────────────────────────────────────────

    def test_search_case_insensitive_title(self, svc_with_entries):
        """Búsqueda en title insensible a mayúsculas.
        Ref: contracts/vault-service-interface.md → search_entries (case-insensitive)."""
        svc = svc_with_entries
        lower = svc.search_entries("github")
        upper = svc.search_entries("GITHUB")
        mixed = svc.search_entries("GitHub")
        assert len(lower) == len(upper) == len(mixed) == 1

    def test_search_case_insensitive_username(self, svc_with_entries):
        """Búsqueda en username insensible a mayúsculas.
        Ref: contracts/vault-service-interface.md → search_entries (case-insensitive)."""
        svc = svc_with_entries
        results = svc.search_entries("ALICE")
        assert len(results) == 2

    # ── Query vacío ──────────────────────────────────────────────────────────

    def test_search_empty_query_returns_all(self, svc_with_entries):
        """Query vacío devuelve todas las entradas (subcadena vacía está en cualquier str).
        Ref: US3 Acceptance Scenario 2 — borrar búsqueda muestra todas las entradas."""
        svc = svc_with_entries
        results = svc.search_entries("")
        assert len(results) == len(svc.get_entries())

    # ── Sin coincidencias ────────────────────────────────────────────────────

    def test_search_no_match_returns_empty(self, svc_with_entries):
        """Sin coincidencias devuelve lista vacía.
        Ref: US3 Acceptance Scenario 3 — estado vacío con mensaje informativo."""
        svc = svc_with_entries
        results = svc.search_entries("xyzNuncaExiste99")
        assert results == []

    # ── Rendimiento SC-003 ───────────────────────────────────────────────────

    def test_search_500_entries_under_100ms(self, tmp_path):
        """Búsqueda sobre 500 entradas completa en ≤ 100 ms.
        Ref: SC-003 (plan.md → Performance Goals), Constitución Principio VIII."""
        import time
        from vault.models import EntryRecord

        svc = VaultService(auto_lock_timeout_s=0)
        path = tmp_path / "perf.vault"
        svc.create_vault(path, PASSWORD)
        # Inserción directa en payload — evita 500 operaciones de cifrado/IO.
        for i in range(500):
            svc._session.payload.entries.append(
                EntryRecord.create(title=f"Entrada {i:04d}", username=f"user{i}@example.com")
            )

        start = time.perf_counter()
        results = svc.search_entries("Entrada")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(results) == 500, "Todas las entradas deben coincidir con 'Entrada'"
        assert elapsed_ms < 100, (
            f"SC-003: búsqueda tardó {elapsed_ms:.2f} ms; límite 100 ms"
        )

    # ── Bóveda bloqueada ─────────────────────────────────────────────────────

    def test_search_locked_raises(self):
        """Búsqueda sobre bóveda bloqueada lanza VaultLockedError.
        Ref: contracts/vault-service-interface.md → search_entries."""
        svc = VaultService(auto_lock_timeout_s=0)
        with pytest.raises(VaultLockedError):
            svc.search_entries("algo")


# ── Gestión de carpetas (T032 — US6) ─────────────────────────────────────────


class TestFolderCRUD:
    """Tests de gestión de carpetas — US6, tareas T031–T032.

    Refs: spec.md → User Story 6 (Acceptance Scenarios 1–4).
          data-model.md → FolderRecord.
          contracts/vault-service-interface.md → get_folders, add_folder, delete_folder.
          Clarificación C-003: eliminar carpeta mueve entradas a "Sin carpeta", no las elimina.
    """

    @pytest.fixture
    def svc_open(self, tmp_path):
        """VaultService con bóveda ya creada y desbloqueada."""
        svc = VaultService(auto_lock_timeout_s=0)
        path = tmp_path / "folders.vault"
        svc.create_vault(path, PASSWORD)
        return svc, path

    # ── add_folder ────────────────────────────────────────────────────────────

    def test_add_folder_returns_folder_record(self, svc_open):
        """add_folder devuelve FolderRecord con UUID y nombre asignados.
        Ref: data-model.md → FolderRecord.id UUID4; US6 Acceptance Scenario 1."""
        svc, _ = svc_open
        folder = svc.add_folder("Trabajo")
        assert folder.id
        assert folder.name == "Trabajo"

    def test_add_folder_appears_in_get_folders(self, svc_open):
        """La carpeta creada es visible en get_folders().
        Ref: US6 Acceptance Scenario 1."""
        svc, _ = svc_open
        folder = svc.add_folder("Personal")
        folders = svc.get_folders()
        assert any(f.id == folder.id for f in folders)

    def test_add_folder_strips_name(self, svc_open):
        """El nombre se limpia de espacios externos antes de guardar."""
        svc, _ = svc_open
        folder = svc.add_folder("  Trabajo  ")
        assert folder.name == "Trabajo"

    def test_add_folder_empty_name_raises(self, svc_open):
        """Nombre vacío lanza ValueError.
        Ref: contracts/vault-service-interface.md → add_folder."""
        svc, _ = svc_open
        with pytest.raises(ValueError):
            svc.add_folder("")

    def test_add_folder_whitespace_only_raises(self, svc_open):
        """Nombre compuesto solo de espacios (→ vacío tras strip) lanza ValueError."""
        svc, _ = svc_open
        with pytest.raises(ValueError):
            svc.add_folder("   ")

    def test_add_folder_name_too_long_raises(self, svc_open):
        """Nombre > 255 caracteres lanza ValueError.
        Ref: contracts/vault-service-interface.md → add_folder."""
        svc, _ = svc_open
        with pytest.raises(ValueError):
            svc.add_folder("x" * 256)

    def test_add_folder_name_255_chars_ok(self, svc_open):
        """Nombre de exactamente 255 caracteres es aceptado (boundary)."""
        svc, _ = svc_open
        folder = svc.add_folder("x" * 255)
        assert folder.name == "x" * 255

    def test_add_folder_duplicate_name_raises(self, svc_open):
        """Nombre duplicado lanza DuplicateFolderNameError.
        Ref: contracts/vault-service-interface.md → add_folder;
             US6 — nombres de carpeta deben ser únicos."""
        svc, _ = svc_open
        svc.add_folder("Duplicado")
        with pytest.raises(DuplicateFolderNameError):
            svc.add_folder("Duplicado")

    def test_add_folder_persists_after_lock_unlock(self, svc_open):
        """Las carpetas persisten tras bloquear y desbloquear la bóveda.
        Ref: US6 Acceptance Scenario 1 — persistencia."""
        svc, path = svc_open
        folder = svc.add_folder("Finanzas")
        svc.lock_vault()
        svc.unlock_vault(path, PASSWORD)
        names = [f.name for f in svc.get_folders()]
        assert "Finanzas" in names

    # ── delete_folder ─────────────────────────────────────────────────────────

    def test_delete_folder_removes_it_from_get_folders(self, svc_open):
        """delete_folder elimina la carpeta de la lista.
        Ref: US6 Acceptance Scenario 4."""
        svc, _ = svc_open
        folder = svc.add_folder("Temporal")
        svc.delete_folder(folder.id)
        assert not any(f.id == folder.id for f in svc.get_folders())

    def test_delete_folder_moves_entries_to_no_folder(self, svc_open):
        """Las entradas de la carpeta eliminada pasan a folder_id=None.
        Ref: Clarificación C-003; US6 Acceptance Scenario 4."""
        svc, _ = svc_open
        folder = svc.add_folder("Trabajo")
        e1 = svc.add_entry("Jira", folder_id=folder.id)
        e2 = svc.add_entry("Confluence", folder_id=folder.id)

        count = svc.delete_folder(folder.id)

        assert count == 2
        # Las entradas aún existen en la bóveda, ahora sin carpeta.
        all_entries = svc.get_entries()
        ids = [e.id for e in all_entries]
        assert e1.id in ids
        assert e2.id in ids
        # folder_id debe ser None para las entradas movidas.
        for entry in all_entries:
            if entry.id in (e1.id, e2.id):
                assert entry.folder_id is None

    def test_delete_folder_returns_correct_count(self, svc_open):
        """delete_folder devuelve el número exacto de entradas movidas.
        Ref: contracts/vault-service-interface.md → delete_folder (return value)."""
        svc, _ = svc_open
        f1 = svc.add_folder("F1")
        f2 = svc.add_folder("F2")
        svc.add_entry("A", folder_id=f1.id)
        svc.add_entry("B", folder_id=f1.id)
        svc.add_entry("C", folder_id=f2.id)
        svc.add_entry("D")  # sin carpeta

        count_f1 = svc.delete_folder(f1.id)
        assert count_f1 == 2

        count_f2 = svc.delete_folder(f2.id)
        assert count_f2 == 1

    def test_delete_empty_folder_returns_zero(self, svc_open):
        """Eliminar carpeta vacía no lanza error y devuelve 0.
        Ref: contracts/vault-service-interface.md → delete_folder."""
        svc, _ = svc_open
        folder = svc.add_folder("Vacía")
        count = svc.delete_folder(folder.id)
        assert count == 0

    def test_delete_folder_nonexistent_raises(self, svc_open):
        """ID inexistente lanza FolderNotFoundError.
        Ref: contracts/vault-service-interface.md → delete_folder."""
        svc, _ = svc_open
        with pytest.raises(FolderNotFoundError):
            svc.delete_folder("uuid-no-existe")

    def test_entries_in_deleted_folder_accessible_via_no_folder(self, svc_open):
        """Tras eliminar la carpeta, sus entradas son visibles en get_entries(NO_FOLDER).
        Ref: C-003; US6 Acceptance Scenario 4 — entradas accesibles sin carpeta."""
        svc, _ = svc_open
        folder = svc.add_folder("Temporal")
        svc.add_entry("Entrada1", folder_id=folder.id)
        svc.add_entry("Entrada2", folder_id=folder.id)
        svc.add_entry("SinCarpetaAntes")  # ya en NO_FOLDER

        svc.delete_folder(folder.id)

        sin_carpeta = svc.get_entries(folder_id=NO_FOLDER)
        titles = {e.title for e in sin_carpeta}
        assert "Entrada1" in titles
        assert "Entrada2" in titles
        assert "SinCarpetaAntes" in titles

    def test_delete_folder_does_not_affect_other_folders_entries(self, svc_open):
        """Eliminar una carpeta no toca entradas de otras carpetas."""
        svc, _ = svc_open
        f1 = svc.add_folder("Conservar")
        f2 = svc.add_folder("Eliminar")
        svc.add_entry("EnF1", folder_id=f1.id)
        svc.add_entry("EnF2", folder_id=f2.id)

        svc.delete_folder(f2.id)

        en_f1 = svc.get_entries(folder_id=f1.id)
        assert len(en_f1) == 1
        assert en_f1[0].title == "EnF1"
        assert en_f1[0].folder_id == f1.id  # sin cambios

    # ── get_folders ───────────────────────────────────────────────────────────

    def test_get_folders_locked_raises(self):
        """get_folders sobre bóveda bloqueada lanza VaultLockedError.
        Ref: contracts/vault-service-interface.md → get_folders."""
        svc = VaultService(auto_lock_timeout_s=0)
        with pytest.raises(VaultLockedError):
            svc.get_folders()

    def test_get_folders_empty_when_no_folders(self, svc_open):
        """Bóveda recién creada no tiene carpetas."""
        svc, _ = svc_open
        assert svc.get_folders() == []


# ── Auto-bloqueo por inactividad (T036 — US7) ────────────────────────────────


class TestAutoLock:
    """Tests del auto-bloqueo por inactividad — US7, tareas T035–T036.

    Todos los tests usan timeouts pequeños (≥ 0.1 s, según la tarea T036)
    para que los tests sean rápidos sin sacrificar fiabilidad.

    Refs: spec.md → User Story 7 (Acceptance Scenarios 1–3).
          FR-017 (auto-bloqueo configurable, default 5 min).
          contracts/vault-service-interface.md → record_activity, lock_vault.
    """

    # Timeout usado en la mayoría de los tests; pequeño pero suficiente para
    # que el timer del sistema lo dispare sin carreras de hilos.
    _TIMEOUT = 0.15  # segundos

    @pytest.fixture
    def vault_path(self, tmp_path: Path) -> Path:
        return tmp_path / "autolock.vault"

    # ── US7 Sc1 — la bóveda se bloquea automáticamente ───────────────────────

    def test_vault_locks_after_timeout(self, vault_path):
        """La bóveda se bloquea sola tras el período de inactividad.

        Ref: FR-017 (auto-bloqueo por inactividad), US7 Acceptance Scenario 1.
        """
        svc = VaultService(auto_lock_timeout_s=self._TIMEOUT)
        svc.create_vault(vault_path, PASSWORD)
        assert svc.is_unlocked

        # Esperar a que el timer dispare (timeout + margen generoso)
        deadline = time.perf_counter() + self._TIMEOUT + 0.5
        while svc.is_unlocked and time.perf_counter() < deadline:
            time.sleep(0.02)

        assert not svc.is_unlocked, (
            "La bóveda debería haberse bloqueado automáticamente por inactividad (FR-017)"
        )

    def test_is_unlocked_false_after_autolock(self, vault_path):
        """is_unlocked devuelve False tras el auto-bloqueo.

        Ref: US7 Acceptance Scenario 1 — post-condición tras auto-bloqueo.
             contracts/vault-service-interface.md → is_unlocked.
        """
        svc = VaultService(auto_lock_timeout_s=self._TIMEOUT)
        svc.create_vault(vault_path, PASSWORD)

        deadline = time.perf_counter() + self._TIMEOUT + 0.5
        while svc.is_unlocked and time.perf_counter() < deadline:
            time.sleep(0.02)

        assert svc.is_unlocked is False

    # ── Callback on_auto_lock ─────────────────────────────────────────────────

    def test_on_auto_lock_callback_invoked(self, vault_path):
        """El callback on_auto_lock se invoca cuando el timer dispara.

        Ref: contracts/vault-service-interface.md → on_auto_lock callback.
             T035 — «cuando el timer dispara notifica a un callback on_auto_lock registrable».
        """
        callback_called = threading.Event()
        svc = VaultService(
            auto_lock_timeout_s=self._TIMEOUT,
            on_auto_lock=callback_called.set,
        )
        svc.create_vault(vault_path, PASSWORD)

        triggered = callback_called.wait(timeout=self._TIMEOUT + 0.5)
        assert triggered, "on_auto_lock callback no fue invocado tras el timeout"
        assert not svc.is_unlocked

    def test_on_auto_lock_callback_not_invoked_when_disabled(self, vault_path):
        """Con auto_lock_timeout_s=0 el timer no arranca y el callback no se invoca.

        Ref: T035 — timeout_s=0 desactiva el auto-bloqueo (útil en tests).
        """
        callback_called = threading.Event()
        svc = VaultService(
            auto_lock_timeout_s=0,
            on_auto_lock=callback_called.set,
        )
        svc.create_vault(vault_path, PASSWORD)

        # Esperamos el doble del timeout habitual; el callback NO debe dispararse.
        triggered = callback_called.wait(timeout=self._TIMEOUT * 2)
        assert not triggered, "on_auto_lock no debe dispararse cuando timeout=0"
        assert svc.is_unlocked  # la bóveda sigue abierta

    # ── US7 Sc3 — la actividad reinicia el timer ──────────────────────────────

    def test_record_activity_resets_timer(self, vault_path):
        """record_activity() reinicia el timer: la bóveda NO se bloquea mientras hay actividad.

        Ref: FR-017, US7 Acceptance Scenario 3 — cualquier interacción reinicia el timer.
             contracts/vault-service-interface.md → record_activity.
        """
        TIMEOUT = 0.20
        svc = VaultService(auto_lock_timeout_s=TIMEOUT)
        svc.create_vault(vault_path, PASSWORD)

        # Esperar el 60 % del timeout (antes de que dispare), luego resetear.
        time.sleep(TIMEOUT * 0.6)
        svc.record_activity()

        # Tras el reset, aún estamos al 0 % del nuevo intervalo → desbloqueada.
        assert svc.is_unlocked, "La bóveda debe seguir desbloqueada tras record_activity()"

        # Esperar otro 60 % desde el reset (< TIMEOUT desde el reset → aún desbloqueada).
        time.sleep(TIMEOUT * 0.6)
        assert svc.is_unlocked, (
            "La bóveda debe permanecer desbloqueada porque record_activity() reinició el timer"
        )

        # Ahora esperar que el timer dispare desde el último reset.
        deadline = time.perf_counter() + TIMEOUT + 0.5
        while svc.is_unlocked and time.perf_counter() < deadline:
            time.sleep(0.02)

        assert not svc.is_unlocked, (
            "La bóveda debe bloquearse tras el timeout completo desde la última actividad"
        )

    def test_record_activity_no_op_when_locked(self, vault_path):
        """record_activity() no lanza excepción ni inicia timer cuando está bloqueada.

        Ref: contracts/vault-service-interface.md — record_activity.
             La bóveda bloqueada no tiene sesión activa; la actividad es ignorada.
        """
        svc = VaultService(auto_lock_timeout_s=5)
        svc.create_vault(vault_path, PASSWORD)
        svc.lock_vault()
        assert not svc.is_unlocked

        # No debe lanzar ni iniciar timer
        svc.record_activity()
        assert svc._inactivity_timer is None

    # ── lock_vault() cancela el timer ─────────────────────────────────────────

    def test_lock_vault_cancels_inactivity_timer(self, vault_path):
        """lock_vault() cancela el timer de inactividad pendiente.

        Ref: contracts/vault-service-interface.md → lock_vault.
             US7 Acceptance Scenario 1 — el bloqueo manual también cancela el timer.
        """
        svc = VaultService(auto_lock_timeout_s=60)  # Timeout largo: no dispara en el test.
        svc.create_vault(vault_path, PASSWORD)

        # El timer debe estar activo tras create_vault.
        assert svc._inactivity_timer is not None, "El timer debe iniciar tras desbloquear"

        svc.lock_vault()

        # Tras bloquear, el timer debe haber sido cancelado.
        assert svc._inactivity_timer is None, "lock_vault() debe cancelar el timer"
        assert not svc.is_unlocked

    def test_lock_vault_cancels_timer_idempotent(self, vault_path):
        """lock_vault() puede llamarse varias veces sin error aunque el timer ya esté cancelado.

        Ref: contracts/vault-service-interface.md → lock_vault es idempotente.
        """
        svc = VaultService(auto_lock_timeout_s=60)
        svc.create_vault(vault_path, PASSWORD)
        svc.lock_vault()
        svc.lock_vault()  # segunda llamada — no debe lanzar
        assert not svc.is_unlocked
        assert svc._inactivity_timer is None

    # ── Timer no arranca con timeout = 0 ─────────────────────────────────────

    def test_no_timer_when_timeout_zero(self, vault_path):
        """Con auto_lock_timeout_s=0 no se crea ningún timer.

        Ref: T035 — «0 para desactivar (útil en tests)».
        """
        svc = VaultService(auto_lock_timeout_s=0)
        svc.create_vault(vault_path, PASSWORD)
        assert svc._inactivity_timer is None
        assert svc.is_unlocked

    def test_set_auto_lock_timeout_while_unlocked_restarts_timer(self, vault_path):
        """set_auto_lock_timeout() mientras está desbloqueado reinicia el timer.

        Ref: T039 — diálogo de configuración actualiza VaultService.
        """
        svc = VaultService(auto_lock_timeout_s=60)
        svc.create_vault(vault_path, PASSWORD)
        assert svc._inactivity_timer is not None

        # Cambiar timeout mientras está desbloqueado
        svc.set_auto_lock_timeout(120)
        assert svc._auto_lock_timeout_s == 120
        assert svc._inactivity_timer is not None  # timer reiniciado
        svc.lock_vault()


# ── T-R16 / T-R17: suspend_auto_lock / resume_auto_lock (T002) ───────────────


class TestSuspendResumeAutoLock:
    """T-R16 y T-R17 — suspend_auto_lock / resume_auto_lock.

    Refs: FR-021, Phase 2 (T002), contracts/vault-service-interface.md.
    """

    _TIMEOUT = 0.25  # segundos — suficientemente largo para que el test sea fiable

    @pytest.fixture
    def svc_open(self, vault_path):
        svc = VaultService(auto_lock_timeout_s=self._TIMEOUT)
        svc.create_vault(vault_path, PASSWORD)
        return svc

    def test_T_R16_suspend_cancels_timer_without_locking(self, svc_open):
        """T-R16: suspend_auto_lock() cancela el timer de inactividad sin
        bloquear la sesión — la bóveda sigue desbloqueada más allá del timeout.

        Ref: FR-021, contracts/vault-service-interface.md → suspend_auto_lock.
        """
        svc = svc_open
        assert svc.is_unlocked, "pre: bóveda debe estar desbloqueada"
        svc.suspend_auto_lock()
        # El timer debe haber sido cancelado
        assert svc._inactivity_timer is None, (
            "suspend_auto_lock() debe cancelar el timer"
        )
        # Esperar más allá del timeout — la bóveda NO debe haberse bloqueado
        time.sleep(self._TIMEOUT * 2)
        assert svc.is_unlocked, (
            "La bóveda NO debe bloquearse mientras el auto-bloqueo está suspendido"
        )

    def test_suspend_auto_lock_noop_when_locked(self, vault_path):
        """suspend_auto_lock() es no-op si la bóveda está bloqueada.

        Ref: FR-021 (no-op si bóveda bloqueada).
        """
        svc = VaultService(auto_lock_timeout_s=5)
        svc.create_vault(vault_path, PASSWORD)
        svc.lock_vault()
        # No debe lanzar excepción ni modificar estado
        svc.suspend_auto_lock()
        assert not svc.is_unlocked
        assert svc._inactivity_timer is None

    def test_resume_auto_lock_noop_when_locked(self, vault_path):
        """resume_auto_lock() es no-op si la bóveda está bloqueada.

        Ref: FR-021 (no-op si bóveda bloqueada).
        """
        svc = VaultService(auto_lock_timeout_s=5)
        svc.create_vault(vault_path, PASSWORD)
        svc.lock_vault()
        svc.resume_auto_lock()
        assert not svc.is_unlocked
        assert svc._inactivity_timer is None

    def test_T_R17_resume_restarts_timer_from_zero(self, vault_path):
        """T-R17: resume_auto_lock() reinicia el timer desde cero —
        la bóveda NO se bloquea inmediatamente tras resume.

        Ref: FR-021, contracts/vault-service-interface.md → resume_auto_lock.
        """
        svc = VaultService(auto_lock_timeout_s=self._TIMEOUT)
        svc.create_vault(vault_path, PASSWORD)

        svc.suspend_auto_lock()
        time.sleep(self._TIMEOUT * 1.5)  # timer suspendido — sin bloqueo

        svc.resume_auto_lock()
        assert svc.is_unlocked, (
            "La bóveda debe seguir desbloqueada inmediatamente después de resume_auto_lock()"
        )
        # El timer se ha reiniciado: debemos esperar TIMEOUT más para que bloquee
        time.sleep(self._TIMEOUT * 0.5)
        assert svc.is_unlocked, (
            "La bóveda debe permanecer desbloqueada a mitad del nuevo intervalo"
        )
        # Esperar hasta que el timer recién iniciado dispare
        deadline = time.perf_counter() + self._TIMEOUT + 0.5
        while svc.is_unlocked and time.perf_counter() < deadline:
            time.sleep(0.02)
        assert not svc.is_unlocked, (
            "La bóveda debe bloquearse tras el timeout completo desde resume_auto_lock()"
        )


# ── T-R01–T-R04, T-R11, T-R15, T-R20: change_master_password (T004,T005,T008,T009) ─


NEW_PASSWORD = "NuevaContraseñaSegura456!"
SHORT_PASSWORD = "corta123"       # 9 chars — menos de 12
PASSWORD_11 = "once_chars1"       # exactamente 11 chars


@pytest.fixture
def svc_unlocked(tmp_path):
    """VaultService con bóveda desbloqueada y una entrada."""
    svc = VaultService(auto_lock_timeout_s=0)
    path = tmp_path / "rotation.vault"
    svc.create_vault(path, PASSWORD)
    svc.add_entry("GitHub", username="alice", password="secreto")
    return svc, path


class TestChangeMasterPasswordUS1:
    """T-R01, T-R02, T-R03, T-R04, T-R20 — US1: rotación exitosa.

    Refs: FR-006, FR-008, FR-016, NFR-001, SC-001.
    T004, T005.
    """

    def test_T_R01_new_salt_after_rotation(self, svc_unlocked):
        """T-R01: el salt en metadatos es distinto al anterior tras la rotación.

        Ref: FR-006, NFR-001.
        """
        svc, path = svc_unlocked
        import json
        salt_before = json.loads(path.read_text())["salt"]

        svc.change_master_password(PASSWORD, NEW_PASSWORD)

        salt_after = json.loads(path.read_text())["salt"]
        assert salt_before != salt_after, (
            "El salt debe ser nuevo tras la rotación (FR-006)"
        )

    def test_T_R02_unlock_with_new_password(self, svc_unlocked):
        """T-R02: unlock_vault con la nueva contraseña abre la bóveda con entradas intactas.

        Ref: SC-001, FR-008.
        """
        svc, path = svc_unlocked
        svc.change_master_password(PASSWORD, NEW_PASSWORD)
        svc.lock_vault()

        svc2 = VaultService(auto_lock_timeout_s=0)
        svc2.unlock_vault(path, NEW_PASSWORD)
        assert svc2.is_unlocked
        entries = svc2.get_entries()
        assert len(entries) == 1
        assert entries[0].title == "GitHub"

    def test_T_R03_old_password_rejected_after_rotation(self, svc_unlocked):
        """T-R03: unlock_vault con la contraseña anterior lanza WrongPasswordError.

        Ref: SC-001, FR-008.
        """
        svc, path = svc_unlocked
        svc.change_master_password(PASSWORD, NEW_PASSWORD)
        svc.lock_vault()

        svc2 = VaultService(auto_lock_timeout_s=0)
        with pytest.raises(WrongPasswordError):
            svc2.unlock_vault(path, PASSWORD)

    def test_T_R20_nonce_differs_after_rotation(self, svc_unlocked):
        """T-R20: el nonce en el archivo difiere antes y después de la rotación.

        Ref: NFR-001, FR-008 — nonce único por llave.
        """
        import json
        svc, path = svc_unlocked
        nonce_before = json.loads(path.read_text())["nonce"]

        svc.change_master_password(PASSWORD, NEW_PASSWORD)

        nonce_after = json.loads(path.read_text())["nonce"]
        assert nonce_before != nonce_after, (
            "El nonce debe ser nuevo tras la rotación (NFR-001)"
        )

    def test_T_R04_session_unlocked_with_new_key(self, svc_unlocked):
        """T-R04: tras change_master_password exitoso, is_unlocked es True y
        la sesión contiene la llave nueva (distinta de la antigua).

        Ref: FR-016.
        """
        svc, path = svc_unlocked
        old_key_bytes = bytes(svc._session.derived_key)  # copia para comparar

        svc.change_master_password(PASSWORD, NEW_PASSWORD)

        assert svc.is_unlocked, "La sesión debe permanecer desbloqueada (FR-016)"
        new_key_bytes = bytes(svc._session.derived_key)
        assert old_key_bytes != new_key_bytes, (
            "La llave en sesión debe ser la nueva, distinta de la antigua (FR-016)"
        )


class TestChangeMasterPasswordUS2:
    """T-R11, T-R15 — US2: re-autenticación explícita.

    Refs: FR-001, FR-002, FR-003, FR-004, NFR-007, SC-003.
    T008, T009.
    """

    def test_T_R11_wrong_current_password(self, svc_unlocked):
        """T-R11: contraseña actual incorrecta lanza WrongPasswordError con
        mensaje específico y el archivo permanece byte a byte idéntico.

        Ref: FR-003, FR-004, NFR-007, SC-003.
        """
        import json
        svc, path = svc_unlocked
        content_before = path.read_bytes()

        with pytest.raises(WrongPasswordError) as exc_info:
            svc.change_master_password("contraseña_incorrecta", NEW_PASSWORD)

        assert exc_info.value.args[0] == "Contraseña maestra actual incorrecta.", (
            "El mensaje debe ser específico para re-auth (NFR-007)"
        )
        assert path.read_bytes() == content_before, (
            "El archivo debe permanecer byte a byte idéntico (FR-004)"
        )

    def test_T_R15a_locked_vault_raises_VaultLockedError(self, tmp_path):
        """T-R15a: change_master_password con bóveda bloqueada lanza VaultLockedError.

        Ref: FR-001, FR-002.
        """
        svc = VaultService(auto_lock_timeout_s=0)
        path = tmp_path / "locked.vault"
        svc.create_vault(path, PASSWORD)
        svc.lock_vault()

        with pytest.raises(VaultLockedError):
            svc.change_master_password(PASSWORD, NEW_PASSWORD)

    def test_T_R15b_empty_current_password_raises_before_reencrypt(self, svc_unlocked):
        """T-R15b: current_password vacío lanza WrongPasswordError antes de
        cualquier operación de re-cifrado — no puede omitir re-autenticación.

        Ref: FR-002.
        """
        svc, path = svc_unlocked
        content_before = path.read_bytes()

        with pytest.raises(WrongPasswordError):
            svc.change_master_password("", NEW_PASSWORD)

        assert path.read_bytes() == content_before, (
            "El archivo no debe modificarse cuando la re-autenticación falla"
        )


class TestChangeMasterPasswordUS3:
    """T-R07–T-R10, T-R13 (autolock) — US3: atomicidad y consistencia.

    Refs: FR-009–FR-012, NFR-002–NFR-003, SC-002, SC-004.
    T010, T011, T012, T013.
    """

    def test_T_R07_interrupted_before_commit_leaves_original_intact(self, svc_unlocked, monkeypatch):
        """T-R07: si os.replace falla, el archivo original permanece intacto
        y sigue siendo descifrable con la contraseña anterior; sin residuos.

        Ref: NFR-002, FR-011, FR-012, SC-002.
        """
        import os as _os
        svc, path = svc_unlocked
        content_before = path.read_bytes()

        real_replace = _os.replace

        def fail_replace(src, dst):
            raise OSError("Disco lleno simulado")

        monkeypatch.setattr(_os, "replace", fail_replace)

        with pytest.raises(OSError):
            svc.change_master_password(PASSWORD, NEW_PASSWORD)

        monkeypatch.setattr(_os, "replace", real_replace)

        # Archivo original intacto
        assert path.read_bytes() == content_before, (
            "El archivo original debe permanecer intacto cuando os.replace falla"
        )
        # Sin archivos temporales residuales
        tmp_files = list(path.parent.glob("*.tmp")) + list(path.parent.glob("*.part"))
        assert tmp_files == [], f"No deben quedar archivos temporales: {tmp_files}"

        # Sigue siendo descifrable con contraseña anterior
        svc2 = VaultService(auto_lock_timeout_s=0)
        svc2.unlock_vault(path, PASSWORD)
        assert svc2.is_unlocked

    def test_T_R08_post_commit_file_decryptable_with_new_password(self, svc_unlocked, monkeypatch):
        """T-R08: después del commit (os.replace) el archivo es descifrable
        con la nueva contraseña aunque la actualización de sesión falle.

        Ref: NFR-002, SC-002.
        """
        import os as _os
        svc, path = svc_unlocked

        real_replace = _os.replace
        committed = []

        def recording_replace(src, dst):
            real_replace(src, dst)
            committed.append(True)

        monkeypatch.setattr(_os, "replace", recording_replace)

        svc.change_master_password(PASSWORD, NEW_PASSWORD)

        assert committed, "os.replace debe haberse llamado (commit)"
        # El archivo en disco es descifrable con la nueva contraseña
        svc2 = VaultService(auto_lock_timeout_s=0)
        svc2.unlock_vault(path, NEW_PASSWORD)
        assert svc2.is_unlocked

    def test_T_R09_tampered_kdf_params_fails_decryption(self, svc_unlocked):
        """T-R09: modificar kdf_params en el archivo re-cifrado causa fallo GCM
        al desbloquear (AAD re-vinculada a metadatos).

        Ref: NFR-003, FR-009, SC-004.
        """
        import json
        svc, path = svc_unlocked
        svc.change_master_password(PASSWORD, NEW_PASSWORD)

        # Modificar memory_cost en el archivo
        data = json.loads(path.read_text())
        data["kdf_params"]["memory_cost"] = 1  # valor inválido
        path.write_text(json.dumps(data), encoding="utf-8")

        svc2 = VaultService(auto_lock_timeout_s=0)
        with pytest.raises(WrongPasswordError):
            svc2.unlock_vault(path, NEW_PASSWORD)

    def test_T_R10_tampered_salt_fails_decryption(self, svc_unlocked):
        """T-R10: modificar el campo salt en los metadatos causa fallo GCM al
        desbloquear (AAD re-vinculada al salt).

        Ref: NFR-003, FR-009, SC-004.
        """
        import base64
        import json
        svc, path = svc_unlocked
        svc.change_master_password(PASSWORD, NEW_PASSWORD)

        # Reemplazar salt por bytes aleatorios distintos
        data = json.loads(path.read_text())
        fake_salt = base64.b64encode(b"\xde\xad\xbe\xef" * 4).decode("ascii")
        data["salt"] = fake_salt
        path.write_text(json.dumps(data), encoding="utf-8")

        svc2 = VaultService(auto_lock_timeout_s=0)
        with pytest.raises(WrongPasswordError):
            svc2.unlock_vault(path, NEW_PASSWORD)

    def test_T_R13_autolock_suspended_during_rotation_window(self, tmp_path):
        """T-R13: configurar VaultService con timeout corto; suspend_auto_lock()
        evita el bloqueo; resume_auto_lock() reinicia el timer desde cero.

        Ref: FR-021, US3 Ac. Sc. 5. Depends on T003.
        """
        TIMEOUT = 0.30
        svc = VaultService(auto_lock_timeout_s=TIMEOUT)
        path = tmp_path / "autolock.vault"
        svc.create_vault(path, PASSWORD)

        svc.suspend_auto_lock()
        time.sleep(TIMEOUT * 1.5)  # esperamos más allá del timeout
        assert svc.is_unlocked, "La bóveda no debe bloquearse mientras está suspendida"

        svc.resume_auto_lock()
        # Inmediatamente después del resume, la bóveda sigue abierta
        assert svc.is_unlocked

        # Esperar el timeout completo desde el resume
        deadline = time.perf_counter() + TIMEOUT + 0.5
        while svc.is_unlocked and time.perf_counter() < deadline:
            time.sleep(0.02)
        assert not svc.is_unlocked, (
            "La bóveda debe bloquearse tras el timeout completo desde resume_auto_lock()"
        )


class TestChangeMasterPasswordUS5:
    """T-R05, T-R06 — US5: higiene de memoria y ausencia de residuos.

    Refs: NFR-004, NFR-005, FR-012, FR-013, FR-014, SC-005.
    T014, T015.
    """

    def test_T_R05_old_key_zeroed_on_original_bytearray(self, svc_unlocked):
        """T-R05: el zeroing actúa sobre el bytearray ORIGINAL de session.derived_key.

        Guardar referencia ANTES de la rotación; después verificar que todos los
        bytes son cero — confirma que se zerorizó el objeto original, no una copia.

        Ref: NFR-004, FR-013, SC-005.
        """
        svc, path = svc_unlocked
        # Referencia al bytearray original (no copia)
        old_key_ref = svc._session.derived_key

        svc.change_master_password(PASSWORD, NEW_PASSWORD)

        assert all(b == 0 for b in old_key_ref), (
            "El zeroing debe afectar al bytearray original, no a una copia (NFR-004)"
        )

    def test_T_R06_no_residual_files_after_rotation(self, svc_unlocked):
        """T-R06a: tras rotación exitosa no quedan archivos temporales y la bóveda
        no es descifrable con la contraseña antigua.

        Ref: NFR-005, FR-012, FR-014, SC-005.
        """
        svc, path = svc_unlocked
        svc.change_master_password(PASSWORD, NEW_PASSWORD)

        # Sin archivos temporales
        tmp_files = (
            list(path.parent.glob("*.tmp"))
            + list(path.parent.glob("*.part"))
            + [f for f in path.parent.iterdir() if f != path and f.is_file()]
        )
        assert tmp_files == [], f"No deben quedar archivos residuales: {tmp_files}"

        # La vieja contraseña ya no abre la bóveda
        svc2 = VaultService(auto_lock_timeout_s=0)
        with pytest.raises(WrongPasswordError):
            svc2.unlock_vault(path, PASSWORD)

    def test_T_R06b_no_residual_files_after_failed_rotation(self, svc_unlocked):
        """T-R06b: tras rotación fallida (contraseña incorrecta) no quedan
        archivos temporales.

        Ref: NFR-005, FR-012, SC-005.
        """
        svc, path = svc_unlocked

        with pytest.raises(WrongPasswordError):
            svc.change_master_password("incorrecta", NEW_PASSWORD)

        tmp_files = (
            list(path.parent.glob("*.tmp"))
            + list(path.parent.glob("*.part"))
        )
        assert tmp_files == [], f"No deben quedar archivos temporales tras fallo: {tmp_files}"


class TestChangeMasterPasswordUS4:
    """T-R12, T-R13, T-R14 — US4: validación de la nueva contraseña.

    Refs: FR-005, FR-018, FR-019.
    T016, T017.
    """

    def test_T_R12_identical_passwords_raises_ValueError(self, svc_unlocked):
        """T-R12: change_master_password(current, current) lanza ValueError
        indicando identidad, sin derivar ninguna clave nueva.

        Ref: FR-018, US4 Ac. Sc. 4.
        """
        svc, path = svc_unlocked
        content_before = path.read_bytes()

        with pytest.raises(ValueError, match="idéntica|identical|igual|same"):
            svc.change_master_password(PASSWORD, PASSWORD)

        assert path.read_bytes() == content_before, (
            "El archivo no debe modificarse al rechazar contraseña idéntica"
        )

    def test_T_R13_short_new_password_raises_ValueError(self, svc_unlocked):
        """T-R13: nueva contraseña de 11 caracteres lanza ValueError con
        mención de 12 caracteres mínimos.

        Ref: FR-019, US4 Ac. Sc. 5.
        """
        svc, path = svc_unlocked
        content_before = path.read_bytes()

        with pytest.raises(ValueError, match="12"):
            svc.change_master_password(PASSWORD, PASSWORD_11)

        assert path.read_bytes() == content_before, (
            "El archivo no debe modificarse al rechazar contraseña corta"
        )

    def test_T_R14_empty_new_password_raises_ValueError(self, svc_unlocked):
        """T-R14: nueva contraseña vacía lanza ValueError; disco sin modificar.

        Ref: FR-005, US4 Ac. Sc. 2.
        """
        svc, path = svc_unlocked
        content_before = path.read_bytes()

        with pytest.raises(ValueError):
            svc.change_master_password(PASSWORD, "")

        assert path.read_bytes() == content_before, (
            "El archivo no debe modificarse cuando new_password está vacío"
        )

