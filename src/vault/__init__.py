"""Exportaciones del paquete vault."""
from vault.exceptions import (
    DuplicateFolderNameError,
    EntryNotFoundError,
    FolderNotFoundError,
    VaultAlreadyExistsError,
    VaultCorruptError,
    VaultLockedError,
    WrongPasswordError,
)
from vault.models import EntryRecord, FolderRecord, VaultPayload, VaultSession
from vault.service import VaultService

__all__ = [
    "VaultService",
    "VaultLockedError",
    "VaultAlreadyExistsError",
    "WrongPasswordError",
    "VaultCorruptError",
    "EntryNotFoundError",
    "FolderNotFoundError",
    "DuplicateFolderNameError",
    "EntryRecord",
    "FolderRecord",
    "VaultPayload",
    "VaultSession",
]
