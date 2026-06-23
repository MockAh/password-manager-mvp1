"""Tests de detección de manipulación — integración (T011).

Verifica que cualquier alteración del archivo de bóveda sea detectada
y se rechace el acceso. Esto es una propiedad de seguridad fundamental
garantizada por AES-256-GCM y el AAD anti-downgrade.

Referencia: Contratos vault-file-format.md, vault-service-interface.md
"""
import base64
import json
from pathlib import Path

import pytest

from vault.exceptions import VaultCorruptError, WrongPasswordError
from vault.service import VaultService

PASSWORD = "ContraseñaMaestraSegura123!"
_EITHER_ERROR = (WrongPasswordError, VaultCorruptError)


@pytest.fixture
def vault_with_file(tmp_path):
    """Crea una bóveda real en disco y devuelve (path, raw_dict)."""
    vault_path = tmp_path / "test.vault"
    svc = VaultService(auto_lock_timeout_s=0)
    svc.create_vault(vault_path, PASSWORD)
    svc.lock_vault()
    raw = json.loads(vault_path.read_text(encoding="utf-8"))
    return vault_path, raw


# ── Casos de detección de manipulación ───────────────────────────────────────


def test_flip_ciphertext_byte_rejected(vault_with_file):
    """Un byte alterado en el ciphertext debe ser rechazado."""
    vault_path, raw = vault_with_file
    ct_bytes = bytearray(base64.b64decode(raw["ciphertext"]))
    ct_bytes[0] ^= 0xFF
    raw["ciphertext"] = base64.b64encode(ct_bytes).decode("ascii")
    vault_path.write_text(json.dumps(raw), encoding="utf-8")

    svc = VaultService(auto_lock_timeout_s=0)
    with pytest.raises(_EITHER_ERROR):
        svc.unlock_vault(vault_path, PASSWORD)


def test_truncated_ciphertext_rejected(vault_with_file):
    """Ciphertext truncado (sin tag GCM) debe ser rechazado."""
    vault_path, raw = vault_with_file
    ct_bytes = base64.b64decode(raw["ciphertext"])
    raw["ciphertext"] = base64.b64encode(ct_bytes[:4]).decode("ascii")
    vault_path.write_text(json.dumps(raw), encoding="utf-8")

    svc = VaultService(auto_lock_timeout_s=0)
    with pytest.raises(_EITHER_ERROR):
        svc.unlock_vault(vault_path, PASSWORD)


def test_modified_kdf_params_memory_cost_rejected(vault_with_file):
    """Reducir kdf_params.memory_cost (ataque de downgrade) debe ser rechazado.
    Propiedad: el AAD incluye kdf_params, por lo que su modificación invalida el tag GCM.
    """
    vault_path, raw = vault_with_file
    raw["kdf_params"]["memory_cost"] = 8  # downgrade a 8 KiB
    vault_path.write_text(json.dumps(raw), encoding="utf-8")

    svc = VaultService(auto_lock_timeout_s=0)
    with pytest.raises(_EITHER_ERROR):
        svc.unlock_vault(vault_path, PASSWORD)


def test_modified_salt_rejected(vault_with_file):
    """Modificar el salt produce una clave diferente → el tag GCM falla."""
    vault_path, raw = vault_with_file
    # Crear un salt válido (16 bytes) pero diferente
    import os
    different_salt = base64.b64encode(os.urandom(16)).decode("ascii")
    raw["salt"] = different_salt
    vault_path.write_text(json.dumps(raw), encoding="utf-8")

    svc = VaultService(auto_lock_timeout_s=0)
    with pytest.raises(_EITHER_ERROR):
        svc.unlock_vault(vault_path, PASSWORD)


def test_modified_nonce_rejected(vault_with_file):
    """Un nonce diferente al usado en cifrado invalida el tag GCM."""
    vault_path, raw = vault_with_file
    import os
    raw["nonce"] = base64.b64encode(os.urandom(12)).decode("ascii")
    vault_path.write_text(json.dumps(raw), encoding="utf-8")

    svc = VaultService(auto_lock_timeout_s=0)
    with pytest.raises(_EITHER_ERROR):
        svc.unlock_vault(vault_path, PASSWORD)


def test_missing_nonce_field_raises_corrupt(vault_with_file):
    """Campo nonce ausente → VaultCorruptError (validación estructural)."""
    vault_path, raw = vault_with_file
    del raw["nonce"]
    vault_path.write_text(json.dumps(raw), encoding="utf-8")

    svc = VaultService(auto_lock_timeout_s=0)
    with pytest.raises(VaultCorruptError):
        svc.unlock_vault(vault_path, PASSWORD)


def test_missing_ciphertext_field_raises_corrupt(vault_with_file):
    vault_path, raw = vault_with_file
    del raw["ciphertext"]
    vault_path.write_text(json.dumps(raw), encoding="utf-8")

    svc = VaultService(auto_lock_timeout_s=0)
    with pytest.raises(VaultCorruptError):
        svc.unlock_vault(vault_path, PASSWORD)


def test_malformed_json_raises_corrupt(vault_with_file):
    """JSON inválido → VaultCorruptError."""
    vault_path, _ = vault_with_file
    vault_path.write_text("{not valid json", encoding="utf-8")

    svc = VaultService(auto_lock_timeout_s=0)
    with pytest.raises(VaultCorruptError):
        svc.unlock_vault(vault_path, PASSWORD)


def test_wrong_kdf_identifier_raises_corrupt(vault_with_file):
    """KDF no soportado → VaultCorruptError (validación estructural)."""
    vault_path, raw = vault_with_file
    raw["kdf"] = "pbkdf2"
    vault_path.write_text(json.dumps(raw), encoding="utf-8")

    svc = VaultService(auto_lock_timeout_s=0)
    with pytest.raises(VaultCorruptError):
        svc.unlock_vault(vault_path, PASSWORD)


def test_wrong_version_raises_corrupt(vault_with_file):
    """Versión no soportada → VaultCorruptError."""
    vault_path, raw = vault_with_file
    raw["version"] = 99
    vault_path.write_text(json.dumps(raw), encoding="utf-8")

    svc = VaultService(auto_lock_timeout_s=0)
    with pytest.raises(VaultCorruptError):
        svc.unlock_vault(vault_path, PASSWORD)
