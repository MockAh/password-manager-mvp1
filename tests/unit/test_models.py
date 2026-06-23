"""Tests de serialización y modelo de datos (T008).
TDD: estos tests se escriben ANTES de la implementación.
"""
import uuid
from pathlib import Path

import pytest

from vault.models import EntryRecord, FolderRecord, VaultPayload, VaultSession


class TestFolderRecord:
    def test_create_generates_uuid(self):
        folder = FolderRecord.create("Trabajo")
        uuid.UUID(folder.id)  # lanza ValueError si no es UUID válido

    def test_create_stores_name(self):
        folder = FolderRecord.create("Personal")
        assert folder.name == "Personal"

    def test_roundtrip_to_dict_from_dict(self):
        original = FolderRecord.create("Banco")
        restored = FolderRecord.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.name == original.name

    def test_to_dict_keys(self):
        d = FolderRecord.create("Test").to_dict()
        assert set(d.keys()) == {"id", "name"}


class TestEntryRecord:
    def test_create_generates_uuid(self):
        entry = EntryRecord.create("GitHub")
        uuid.UUID(entry.id)

    def test_create_defaults(self):
        entry = EntryRecord.create("GitHub")
        assert entry.title == "GitHub"
        assert entry.username == ""
        assert entry.password == ""
        assert entry.url == ""
        assert entry.notes == ""
        assert entry.folder_id is None

    def test_create_with_all_fields(self):
        entry = EntryRecord.create(
            title="GitHub",
            username="user@example.com",
            password="s3cr3t",
            url="https://github.com",
            notes="Mi cuenta principal",
            folder_id="some-folder-uuid",
        )
        assert entry.username == "user@example.com"
        assert entry.password == "s3cr3t"
        assert entry.url == "https://github.com"
        assert entry.notes == "Mi cuenta principal"
        assert entry.folder_id == "some-folder-uuid"

    def test_created_at_is_set_on_creation(self):
        entry = EntryRecord.create("Test")
        assert entry.created_at is not None
        assert len(entry.created_at) > 0

    def test_updated_at_equals_created_at_on_creation(self):
        entry = EntryRecord.create("Test")
        assert entry.updated_at == entry.created_at

    def test_created_at_is_invariant_through_roundtrip(self):
        """created_at no se modifica al hacer from_dict."""
        original = EntryRecord.create("GitHub")
        d = original.to_dict()
        restored = EntryRecord.from_dict(d)
        assert restored.created_at == original.created_at

    def test_updated_at_preserved_in_roundtrip(self):
        original = EntryRecord.create("GitHub")
        d = original.to_dict()
        d["updated_at"] = "2026-06-17T10:30:00+00:00"
        restored = EntryRecord.from_dict(d)
        assert restored.updated_at == "2026-06-17T10:30:00+00:00"

    def test_roundtrip_to_dict_from_dict(self):
        original = EntryRecord.create(
            title="GitLab",
            username="dev@example.com",
            password="pass123",
            url="https://gitlab.com",
            notes="Notas",
            folder_id="folder-1",
        )
        restored = EntryRecord.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.title == original.title
        assert restored.username == original.username
        assert restored.password == original.password
        assert restored.url == original.url
        assert restored.notes == original.notes
        assert restored.folder_id == original.folder_id
        assert restored.created_at == original.created_at
        assert restored.updated_at == original.updated_at

    def test_to_dict_keys(self):
        d = EntryRecord.create("Test").to_dict()
        expected = {"id", "title", "username", "password", "url", "notes",
                    "folder_id", "created_at", "updated_at"}
        assert set(d.keys()) == expected

    def test_folder_id_can_be_none(self):
        entry = EntryRecord.create("Test")
        d = entry.to_dict()
        assert d["folder_id"] is None
        restored = EntryRecord.from_dict(d)
        assert restored.folder_id is None


class TestVaultPayload:
    def test_empty_payload_roundtrip(self):
        payload = VaultPayload(folders=[], entries=[])
        restored = VaultPayload.from_dict(payload.to_dict())
        assert restored.folders == []
        assert restored.entries == []

    def test_payload_with_folders_and_entries(self):
        folder = FolderRecord.create("Trabajo")
        entry = EntryRecord.create("GitHub", username="user")
        payload = VaultPayload(folders=[folder], entries=[entry])
        d = payload.to_dict()
        restored = VaultPayload.from_dict(d)
        assert len(restored.folders) == 1
        assert restored.folders[0].id == folder.id
        assert restored.folders[0].name == folder.name
        assert len(restored.entries) == 1
        assert restored.entries[0].id == entry.id
        assert restored.entries[0].username == "user"

    def test_to_dict_keys(self):
        d = VaultPayload(folders=[], entries=[]).to_dict()
        assert set(d.keys()) == {"folders", "entries"}


class TestVaultSession:
    def _make_session(self) -> VaultSession:
        return VaultSession(
            derived_key=bytearray(b"\xAB" * 32),
            vault_file_path=Path("/tmp/test.vault"),
            payload=VaultPayload(folders=[], entries=[]),
            salt_b64="dGVzdHNhbHQxMjM0NTY=",
            kdf_params={"time_cost": 3, "memory_cost": 65536, "parallelism": 1, "hash_len": 32},
        )

    def test_zero_key_overwrites_with_zeros(self):
        session = self._make_session()
        assert any(b != 0 for b in session.derived_key)
        session.zero_key()
        assert all(b == 0 for b in session.derived_key)

    def test_zero_key_modifies_in_place(self):
        """zero_key() modifica el bytearray en lugar (no crea una copia)."""
        session = self._make_session()
        key_ref = session.derived_key
        session.zero_key()
        assert all(b == 0 for b in key_ref)  # misma referencia, ahora ceros

    def test_zero_key_length_unchanged(self):
        session = self._make_session()
        session.zero_key()
        assert len(session.derived_key) == 32
