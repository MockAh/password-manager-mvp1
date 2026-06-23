"""Fixtures compartidas para todos los tests."""
import pytest
from pathlib import Path


@pytest.fixture
def vault_password() -> str:
    return "ContraseñaMaestraSegura123!"


@pytest.fixture
def tmp_vault_path(tmp_path: Path) -> Path:
    return tmp_path / "test.vault"


@pytest.fixture
def vault_service():
    """VaultService con auto-bloqueo desactivado para tests."""
    from vault.service import VaultService
    return VaultService(auto_lock_timeout_s=0)


@pytest.fixture
def created_and_locked_vault(tmp_vault_path, vault_password, vault_service):
    """Servicio con bóveda creada y bloqueada, listo para unlock."""
    vault_service.create_vault(tmp_vault_path, vault_password)
    vault_service.lock_vault()
    return vault_service, tmp_vault_path, vault_password
