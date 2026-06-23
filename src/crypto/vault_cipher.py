"""Módulo de cifrado autenticado AES-256-GCM.

Único módulo autorizado para cifrar/descifrar el payload de la bóveda.
Ningún otro módulo llama directamente a AESGCM.

Constitución: Principio III — Cifrado autenticado (AEAD) + AAD anti-downgrade KDF.
Referencia: NIST SP 800-38D — Recommendation for Block Cipher Modes of Operation: GCM.

AAD (datos adicionales autenticados):
  Los campos version, kdf, kdf_params y salt del envelope se incluyen como AAD.
  Esto impide ataques de downgrade: si un atacante reduce kdf_params.memory_cost
  para facilitar fuerza bruta, el tag GCM falla al descifrar porque el AAD
  calculado en descifrado difiere del usado en cifrado.
"""
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def build_aad(version: int, kdf: str, kdf_params: dict, salt_b64: str) -> bytes:
    """Construye los datos adicionales autenticados (AAD) para AES-256-GCM.

    Serializa los campos del envelope como JSON canónico (sort_keys=True,
    sin espacios) en UTF-8, garantizando que el AAD sea idéntico al cifrar
    y al descifrar siempre que el archivo no haya sido modificado.

    Args:
        version: Versión de formato del vault (int).
        kdf: Identificador del algoritmo KDF (str).
        kdf_params: Dict con parámetros de la KDF.
        salt_b64: Salt en base64 (str).

    Returns:
        bytes con el JSON canónico del envelope (UTF-8).
    """
    envelope = {
        "kdf": kdf,
        "kdf_params": kdf_params,
        "salt": salt_b64,
        "version": version,
    }
    return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")


def encrypt(
    plaintext: bytes,
    key: bytes | bytearray,
    envelope_meta: dict,
) -> tuple[bytes, bytes]:
    """Cifra plaintext con AES-256-GCM usando los campos del envelope como AAD.

    Args:
        plaintext: Datos a cifrar (payload JSON de VaultPayload en UTF-8).
        key: Clave AES-256 de 32 bytes (de derive_key).
        envelope_meta: Dict con version, kdf, kdf_params, salt (los campos
                       que se almacenan en texto plano en el archivo de bóveda).

    Returns:
        Tupla (nonce: bytes, ciphertext_with_tag: bytes).
        - nonce: 12 bytes aleatorios — almacenar junto al ciphertext.
        - ciphertext_with_tag: ciphertext + 16-byte authentication tag (GCM).

    Genera un nonce fresco con os.urandom(12) en cada llamada.
    """
    nonce = os.urandom(12)
    aad = build_aad(
        envelope_meta["version"],
        envelope_meta["kdf"],
        envelope_meta["kdf_params"],
        envelope_meta["salt"],
    )
    aesgcm = AESGCM(bytes(key))
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ciphertext_with_tag


def decrypt(
    ciphertext_with_tag: bytes,
    nonce: bytes,
    key: bytes | bytearray,
    envelope_meta: dict,
) -> bytes:
    """Descifra y verifica la autenticidad del ciphertext con AES-256-GCM.

    Args:
        ciphertext_with_tag: Ciphertext + authentication tag (16 bytes finales).
        nonce: Nonce de 12 bytes del archivo de bóveda.
        key: Clave AES-256 de 32 bytes.
        envelope_meta: Dict con version, kdf, kdf_params, salt — debe ser
                       idéntico al usado durante el cifrado.

    Returns:
        Plaintext descifrado (bytes).

    Raises:
        cryptography.exceptions.InvalidTag: Si la contraseña es incorrecta,
            si el ciphertext ha sido manipulado, o si cualquier campo del
            envelope incluido en el AAD ha sido modificado.
    """
    aad = build_aad(
        envelope_meta["version"],
        envelope_meta["kdf"],
        envelope_meta["kdf_params"],
        envelope_meta["salt"],
    )
    aesgcm = AESGCM(bytes(key))
    return aesgcm.decrypt(nonce, ciphertext_with_tag, aad)
