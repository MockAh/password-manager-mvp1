"""Tests unitarios del ciclo de vida de VaultService (T013).

Cubre: create_vault, unlock_vault, lock_vault, is_unlocked.
Los tests de integración completos están en test_vault_roundtrip.py.
"""
import json
from pathlib import Path

import pytest

from vault.exceptions import (
    VaultAlreadyExistsError,
    VaultCorruptError,
    VaultLockedError,
    WrongPasswordError,
)
from vault.service import VaultService

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
