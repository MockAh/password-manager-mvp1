"""Exportaciones públicas del módulo crypto.

Único punto de entrada para las primitivas criptográficas del proyecto.
El resto del código importa desde aquí, no directamente desde kdf o vault_cipher.
"""
from crypto.kdf import derive_key, generate_salt
from crypto.vault_cipher import build_aad, decrypt, encrypt

__all__ = [
    "derive_key",
    "generate_salt",
    "build_aad",
    "encrypt",
    "decrypt",
]
