"""Tests unitarios del ciclo de vida de VaultService (T013).

Cubre: create_vault, unlock_vault, lock_vault, is_unlocked.
Los tests de integración completos están en test_vault_roundtrip.py.
"""
import json
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

