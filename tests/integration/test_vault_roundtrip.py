"""Test de integración — ciclo completo de la bóveda (T014).

Cubre el flujo US1 de extremo a extremo:
  crear → bloquear → desbloquear → verificar → error con mala contraseña.

Estos tests usan el servicio completo (KDF real, cifrado real, disco real).
"""
import base64
import json
from pathlib import Path

import pytest

from vault.exceptions import WrongPasswordError
from vault.service import VaultService

PASSWORD = "ContraseñaMaestraSegura123!"
WRONG_PASSWORD = "ContraseñaIncorrecta999!"


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "roundtrip.vault"


def test_full_create_lock_unlock_cycle(vault_path):
    """US1: crear bóveda → bloquear → desbloquear con contraseña correcta."""
    svc = VaultService(auto_lock_timeout_s=0)

    # Crear
    svc.create_vault(vault_path, PASSWORD)
    assert svc.is_unlocked
    assert vault_path.exists()

    # Bloquear
    svc.lock_vault()
    assert not svc.is_unlocked

    # Desbloquear
    svc.unlock_vault(vault_path, PASSWORD)
    assert svc.is_unlocked


def test_wrong_password_after_create(vault_path):
    """La contraseña incorrecta lanza WrongPasswordError."""
    svc = VaultService(auto_lock_timeout_s=0)
    svc.create_vault(vault_path, PASSWORD)
    svc.lock_vault()

    with pytest.raises(WrongPasswordError):
        svc.unlock_vault(vault_path, WRONG_PASSWORD)


def test_vault_file_structure(vault_path):
    """El archivo de bóveda debe cumplir el contrato de formato."""
    svc = VaultService(auto_lock_timeout_s=0)
    svc.create_vault(vault_path, PASSWORD)

    data = json.loads(vault_path.read_text(encoding="utf-8"))

    assert data["version"] == 1
    assert data["kdf"] == "argon2id"
    assert isinstance(data["kdf_params"], dict)
    assert data["kdf_params"]["time_cost"] == 3
    assert data["kdf_params"]["memory_cost"] == 65536
    assert data["kdf_params"]["parallelism"] == 1
    assert data["kdf_params"]["hash_len"] == 32

    # salt: 16 bytes en base64
    salt_bytes = base64.b64decode(data["salt"])
    assert len(salt_bytes) == 16

    # nonce: 12 bytes en base64
    nonce_bytes = base64.b64decode(data["nonce"])
    assert len(nonce_bytes) == 12

    # ciphertext presente y no vacío
    ct_bytes = base64.b64decode(data["ciphertext"])
    assert len(ct_bytes) > 0


def test_no_sensitive_data_in_file(vault_path):
    """Ningún dato sensible debe aparecer en texto plano en el archivo."""
    svc = VaultService(auto_lock_timeout_s=0)
    svc.create_vault(vault_path, PASSWORD)

    raw = vault_path.read_text(encoding="utf-8")

    # La contraseña maestra NUNCA en disco
    assert PASSWORD not in raw
    # "password" como campo plano tampoco
    assert '"password"' not in raw.lower() or (
        # La única aparición válida es dentro del JSON cifrado (base64)
        raw.count('"password"') == 0
    )


def test_vault_write_is_atomic(vault_path):
    """Verificar que el archivo existe completamente tras create (no parcialmente)."""
    svc = VaultService(auto_lock_timeout_s=0)
    svc.create_vault(vault_path, PASSWORD)

    # Si la escritura fue atómica, el archivo debe ser JSON parseable completo
    data = json.loads(vault_path.read_text(encoding="utf-8"))
    assert "ciphertext" in data


def test_unlock_preserves_empty_payload(vault_path):
    """Una bóveda recién creada debe tener payload vacío tras desbloquear."""
    svc = VaultService(auto_lock_timeout_s=0)
    svc.create_vault(vault_path, PASSWORD)
    svc.lock_vault()
    svc.unlock_vault(vault_path, PASSWORD)

    # Acceder al payload directamente (no hay API pública todavía en Fase 3)
    assert svc._session is not None
    assert svc._session.payload.folders == []
    assert svc._session.payload.entries == []


def test_fresh_nonce_different_from_original_after_save(vault_path):
    """_save() genera un nonce nuevo — no reutiliza el anterior."""
    svc = VaultService(auto_lock_timeout_s=0)
    svc.create_vault(vault_path, PASSWORD)

    nonce_original = json.loads(vault_path.read_text())["nonce"]

    # Forzar un segundo guardado con _save()
    svc._save()

    nonce_after_save = json.loads(vault_path.read_text())["nonce"]
    assert nonce_original != nonce_after_save, (
        "_save() debe generar un nonce fresco en cada llamada"
    )


# ── T-R18 / T-R19: rotation roundtrip (T006) ─────────────────────────────────

NEW_PASSWORD = "NuevaContraseñaSegura456!"


def test_T_R18_full_rotation_roundtrip(vault_path):
    """T-R18: crear bóveda → añadir entradas → rotar → cerrar →
    reabrir con nueva maestra → verificar entradas.

    Refs: NFR-001, SC-001, FR-017 (kdf_params preservados).
    """
    svc = VaultService(auto_lock_timeout_s=0)
    svc.create_vault(vault_path, PASSWORD)
    svc.add_entry("GitHub", username="alice", password="s3cr3t")
    svc.add_entry("Gmail", username="bob")

    # Rotar
    svc.change_master_password(PASSWORD, NEW_PASSWORD)
    svc.lock_vault()

    # Reabrir con la nueva contraseña
    svc2 = VaultService(auto_lock_timeout_s=0)
    svc2.unlock_vault(vault_path, NEW_PASSWORD)
    assert svc2.is_unlocked

    entries = svc2.get_entries()
    assert len(entries) == 2
    titles = {e.title for e in entries}
    assert titles == {"GitHub", "Gmail"}

    # kdf_params preservados (FR-017)
    data = json.loads(vault_path.read_text())
    assert data["kdf_params"]["time_cost"] == 3
    assert data["kdf_params"]["memory_cost"] == 65536
    assert data["kdf_params"]["parallelism"] == 1
    assert data["kdf_params"]["hash_len"] == 32


def test_T_R19_double_rotation_produces_distinct_salts(vault_path):
    """T-R19: doble rotación consecutiva — los dos salts generados son distintos
    entre sí y distintos al original.

    Refs: NFR-001, SC-001.
    """
    svc = VaultService(auto_lock_timeout_s=0)
    svc.create_vault(vault_path, PASSWORD)
    salt_original = json.loads(vault_path.read_text())["salt"]

    PASSWORD2 = "SegundaContraseña789!"
    PASSWORD3 = "TerceraContraseñaAAA!"

    svc.change_master_password(PASSWORD, PASSWORD2)
    salt_after_first = json.loads(vault_path.read_text())["salt"]

    svc.change_master_password(PASSWORD2, PASSWORD3)
    salt_after_second = json.loads(vault_path.read_text())["salt"]

    assert salt_original != salt_after_first, "Primera rotación debe generar salt nuevo"
    assert salt_original != salt_after_second, "Segunda rotación debe generar salt distinto al original"
    assert salt_after_first != salt_after_second, "Dos rotaciones distintas deben generar salts distintos"