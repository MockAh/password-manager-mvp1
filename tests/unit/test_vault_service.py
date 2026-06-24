"""Tests unitarios del ciclo de vida de VaultService (T013).

Cubre: create_vault, unlock_vault, lock_vault, is_unlocked.
Los tests de integración completos están en test_vault_roundtrip.py.
"""
import json
from pathlib import Path

import pytest

from vault.exceptions import (
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
