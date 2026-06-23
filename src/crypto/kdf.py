"""Módulo de derivación de clave (KDF) — Argon2id.

Único módulo autorizado para derivar claves desde contraseñas de usuario.
Ningún otro módulo llama directamente a argon2.

Referencia: RFC 9106 — Argon2 Memory-Hard Function
Constitución: Principio III — KDF resistente a fuerza bruta con salt único.
"""
import os

from argon2.low_level import Type, hash_secret_raw

# ── Parámetros Argon2id calibrados para hardware de escritorio estándar ──────
# Tiempo esperado en CPU de escritorio (2018-2024): ~200-350 ms
# Cumple: mínimo constitucional ≥ 100 ms y máximo de desbloqueo ≤ 1 s.
ARGON2_TIME_COST    = 3        # iteraciones
ARGON2_MEMORY_COST  = 65536    # KiB (64 MB) — memory-hard
ARGON2_PARALLELISM  = 1        # hilos paralelos
ARGON2_HASH_LEN     = 32       # bytes de salida (256 bits = clave AES-256)
ARGON2_SALT_LEN     = 16       # bytes de salt (128 bits, mínimo constitucional)


def generate_salt() -> bytes:
    """Genera un salt criptográficamente aleatorio de 16 bytes.

    Usa os.urandom (CSPRNG del sistema operativo).
    Cada bóveda debe tener un salt único generado en su creación.
    El salt NO es secreto — se almacena en el archivo de bóveda.
    """
    return os.urandom(ARGON2_SALT_LEN)


def derive_key(password: str, salt: bytes) -> bytearray:
    """Deriva una clave AES-256 desde la contraseña maestra usando Argon2id.

    Args:
        password: Contraseña maestra del usuario (UTF-8).
        salt: Salt único de la bóveda (16 bytes).

    Returns:
        bytearray de 32 bytes con la clave derivada.
        Se devuelve bytearray (mutable) para permitir la sobreescritura con ceros
        al bloquear la bóveda (VaultSession.zero_key()).

    La clave derivada NUNCA debe almacenarse en disco.
    """
    raw: bytes = hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN,
        type=Type.ID,
    )
    return bytearray(raw)
