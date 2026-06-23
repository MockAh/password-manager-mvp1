"""Tests de seguridad AEAD para vault_cipher (T006).
TDD: estos tests se escriben ANTES de la implementación.

Propiedades verificadas:
- Roundtrip cifrado/descifrado correcto
- Contraseña incorrecta → InvalidTag
- Flip de byte en ciphertext → InvalidTag
- Modificar kdf_params en AAD → InvalidTag (anti-downgrade KDF)
- Modificar version en AAD → InvalidTag
- Nonce truncado → InvalidTag / ValueError
- Ciphertext vacío → InvalidTag / ValueError
"""
import os

import pytest
from cryptography.exceptions import InvalidTag

from crypto.vault_cipher import build_aad, decrypt, encrypt

# ── Fixture de metadatos de envelope ─────────────────────────────────────────

SAMPLE_ENVELOPE = {
    "version": 1,
    "kdf": "argon2id",
    "kdf_params": {
        "time_cost": 3,
        "memory_cost": 65536,
        "parallelism": 1,
        "hash_len": 32,
    },
    "salt": "dGVzdHNhbHQxMjM0NTY=",  # base64 válido (16 bytes)
}


def fresh_key() -> bytes:
    return os.urandom(32)


# ── Tests de build_aad ────────────────────────────────────────────────────────


class TestBuildAad:
    def test_returns_bytes(self):
        aad = build_aad(
            SAMPLE_ENVELOPE["version"],
            SAMPLE_ENVELOPE["kdf"],
            SAMPLE_ENVELOPE["kdf_params"],
            SAMPLE_ENVELOPE["salt"],
        )
        assert isinstance(aad, bytes)

    def test_deterministic(self):
        """El mismo input siempre produce el mismo AAD."""
        aad1 = build_aad(1, "argon2id", SAMPLE_ENVELOPE["kdf_params"], "salt==")
        aad2 = build_aad(1, "argon2id", SAMPLE_ENVELOPE["kdf_params"], "salt==")
        assert aad1 == aad2

    def test_different_memory_cost_produces_different_aad(self):
        params_a = dict(SAMPLE_ENVELOPE["kdf_params"])
        params_b = dict(SAMPLE_ENVELOPE["kdf_params"])
        params_b["memory_cost"] = 8
        aad_a = build_aad(1, "argon2id", params_a, "salt==")
        aad_b = build_aad(1, "argon2id", params_b, "salt==")
        assert aad_a != aad_b

    def test_different_version_produces_different_aad(self):
        aad_v1 = build_aad(1, "argon2id", SAMPLE_ENVELOPE["kdf_params"], "salt==")
        aad_v2 = build_aad(2, "argon2id", SAMPLE_ENVELOPE["kdf_params"], "salt==")
        assert aad_v1 != aad_v2


# ── Tests de encrypt / decrypt ────────────────────────────────────────────────


class TestEncryptDecrypt:
    def test_roundtrip(self):
        key = fresh_key()
        plaintext = b"datos secretos de credenciales"
        nonce, ct = encrypt(plaintext, key, SAMPLE_ENVELOPE)
        result = decrypt(ct, nonce, key, SAMPLE_ENVELOPE)
        assert result == plaintext

    def test_returns_nonce_12_bytes(self):
        key = fresh_key()
        nonce, _ = encrypt(b"datos", key, SAMPLE_ENVELOPE)
        assert len(nonce) == 12

    def test_different_nonces_each_call(self):
        key = fresh_key()
        nonce1, _ = encrypt(b"datos", key, SAMPLE_ENVELOPE)
        nonce2, _ = encrypt(b"datos", key, SAMPLE_ENVELOPE)
        assert nonce1 != nonce2, "Cada cifrado debe usar un nonce único"

    def test_wrong_key_raises_invalid_tag(self):
        key = fresh_key()
        wrong_key = fresh_key()
        nonce, ct = encrypt(b"datos", key, SAMPLE_ENVELOPE)
        with pytest.raises(InvalidTag):
            decrypt(ct, nonce, wrong_key, SAMPLE_ENVELOPE)

    def test_flipped_ciphertext_byte_raises_invalid_tag(self):
        key = fresh_key()
        nonce, ct = encrypt(b"datos secretos largos para prueba", key, SAMPLE_ENVELOPE)
        tampered = bytearray(ct)
        tampered[0] ^= 0xFF
        with pytest.raises(InvalidTag):
            decrypt(bytes(tampered), nonce, key, SAMPLE_ENVELOPE)

    def test_modified_kdf_params_in_aad_raises_invalid_tag(self):
        """Anti-downgrade KDF: modificar memory_cost en el AAD debe causar InvalidTag."""
        key = fresh_key()
        nonce, ct = encrypt(b"datos", key, SAMPLE_ENVELOPE)
        # Simular ataque de downgrade: reducir memory_cost
        tampered_meta = {
            **SAMPLE_ENVELOPE,
            "kdf_params": {**SAMPLE_ENVELOPE["kdf_params"], "memory_cost": 8},
        }
        with pytest.raises(InvalidTag):
            decrypt(ct, nonce, key, tampered_meta)

    def test_modified_version_in_aad_raises_invalid_tag(self):
        key = fresh_key()
        nonce, ct = encrypt(b"datos", key, SAMPLE_ENVELOPE)
        tampered_meta = {**SAMPLE_ENVELOPE, "version": 99}
        with pytest.raises(InvalidTag):
            decrypt(ct, nonce, key, tampered_meta)

    def test_truncated_nonce_raises(self):
        key = fresh_key()
        nonce, ct = encrypt(b"datos", key, SAMPLE_ENVELOPE)
        with pytest.raises((InvalidTag, ValueError)):
            decrypt(ct, nonce[:6], key, SAMPLE_ENVELOPE)

    def test_empty_ciphertext_raises(self):
        key = fresh_key()
        with pytest.raises((InvalidTag, ValueError)):
            decrypt(b"", b"\x00" * 12, key, SAMPLE_ENVELOPE)

    def test_ciphertext_includes_authentication_tag(self):
        """El ciphertext devuelto debe incluir el tag GCM (≥ 16 bytes extra)."""
        key = fresh_key()
        plaintext = b"hola"
        _, ct = encrypt(plaintext, key, SAMPLE_ENVELOPE)
        # ciphertext = plaintext_len + 16 bytes de tag GCM
        assert len(ct) == len(plaintext) + 16

    def test_accepts_bytearray_key(self):
        """La clave puede ser bytearray (como la devuelve derive_key)."""
        key = bytearray(os.urandom(32))
        nonce, ct = encrypt(b"datos", key, SAMPLE_ENVELOPE)
        result = decrypt(ct, nonce, key, SAMPLE_ENVELOPE)
        assert result == b"datos"
