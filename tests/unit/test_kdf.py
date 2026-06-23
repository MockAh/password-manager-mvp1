"""Tests de seguridad para la KDF Argon2id (T004).
TDD: estos tests se escriben ANTES de la implementación.
"""
import os
import time

import pytest

from crypto.kdf import (
    ARGON2_HASH_LEN,
    ARGON2_MEMORY_COST,
    ARGON2_PARALLELISM,
    ARGON2_SALT_LEN,
    ARGON2_TIME_COST,
    derive_key,
    generate_salt,
)


class TestGenerateSalt:
    def test_salt_length_is_16_bytes(self):
        salt = generate_salt()
        assert len(salt) == 16

    def test_salt_is_bytes(self):
        salt = generate_salt()
        assert isinstance(salt, bytes)

    def test_consecutive_salts_are_unique(self):
        salts = {generate_salt() for _ in range(20)}
        assert len(salts) == 20, "generate_salt debe producir valores únicos"


class TestDeriveKey:
    def test_returns_bytearray(self):
        salt = generate_salt()
        key = derive_key("contraseña", salt)
        assert isinstance(key, bytearray)

    def test_output_length_is_32_bytes(self):
        salt = generate_salt()
        key = derive_key("contraseña", salt)
        assert len(key) == 32

    def test_derivation_is_deterministic(self):
        """El mismo password + salt siempre produce la misma clave."""
        salt = generate_salt()
        key1 = derive_key("mi_contraseña_secreta", salt)
        key2 = derive_key("mi_contraseña_secreta", salt)
        assert key1 == key2

    def test_different_passwords_produce_different_keys(self):
        salt = generate_salt()
        key1 = derive_key("contraseña_A", salt)
        key2 = derive_key("contraseña_B", salt)
        assert key1 != key2

    def test_different_salts_produce_different_keys(self):
        password = "misma_contraseña"
        key1 = derive_key(password, generate_salt())
        key2 = derive_key(password, generate_salt())
        assert key1 != key2

    def test_key_is_zeroable(self):
        """La clave derivada en bytearray puede sobreescribirse con ceros."""
        salt = generate_salt()
        key = derive_key("contraseña", salt)
        original = bytes(key)
        for i in range(len(key)):
            key[i] = 0
        assert bytes(key) == b"\x00" * 32
        assert bytes(key) != original

    def test_kdf_minimum_duration(self):
        """La derivación DEBE tardar ≥ 100 ms (requisito de seguridad constitucional).
        Propiedad: resistencia a fuerza bruta garantizada por coste de tiempo.
        """
        salt = generate_salt()
        start = time.perf_counter()
        derive_key("contraseña_de_prueba_timing", salt)
        elapsed = time.perf_counter() - start
        assert elapsed >= 0.1, (
            f"KDF tomó {elapsed:.3f}s — debe tardar ≥ 0.1s. "
            "Ajustar parámetros Argon2id para cumplir el requisito de seguridad."
        )


class TestArgon2Params:
    def test_default_time_cost(self):
        assert ARGON2_TIME_COST == 3

    def test_default_memory_cost(self):
        assert ARGON2_MEMORY_COST == 65536  # 64 MB

    def test_default_parallelism(self):
        assert ARGON2_PARALLELISM == 1

    def test_default_hash_len(self):
        assert ARGON2_HASH_LEN == 32  # 256 bits — tamaño clave AES-256

    def test_default_salt_len(self):
        assert ARGON2_SALT_LEN == 16  # 128 bits — mínimo constitucional
