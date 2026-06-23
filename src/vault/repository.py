"""Acceso a disco para archivos de bóveda.

Responsabilidades:
  - Leer un archivo de bóveda y validar su estructura (NO descifra).
  - Escribir un archivo de bóveda de forma atómica (tempfile + os.replace).

La validación aquí es sólo estructural (campos, tamaños, versión).
La validación criptográfica (tag GCM) ocurre en vault_cipher.decrypt.

Constitución: Principio I — escritura atómica para evitar corrupción.
              Principio II — ningún acceso de red.
"""
import base64
import json
import os
import tempfile
from pathlib import Path

from vault.exceptions import VaultCorruptError

_REQUIRED_FIELDS = frozenset({"version", "kdf", "kdf_params", "salt", "nonce", "ciphertext"})
_REQUIRED_KDF_PARAMS = frozenset({"time_cost", "memory_cost", "parallelism", "hash_len"})


def load_vault_file(path: Path) -> dict:
    """Lee y valida estructuralmente el archivo de bóveda.

    Valida:
      - El archivo existe y es JSON válido.
      - Los campos obligatorios están presentes.
      - version == 1.
      - kdf == "argon2id".
      - kdf_params contiene todos los campos necesarios, hash_len == 32.
      - salt decodificado tiene 16 bytes.
      - nonce decodificado tiene 12 bytes.

    Args:
        path: Ruta al archivo .vault.

    Returns:
        dict con el contenido del archivo (sin descifrar).

    Raises:
        VaultCorruptError: Si el archivo no es válido estructuralmente.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, IOError) as exc:
        raise VaultCorruptError(f"No se puede leer el archivo de bóveda: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VaultCorruptError(f"El archivo de bóveda contiene JSON no válido: {exc}") from exc

    if not isinstance(data, dict):
        raise VaultCorruptError("El archivo de bóveda debe ser un objeto JSON.")

    missing = _REQUIRED_FIELDS - data.keys()
    if missing:
        raise VaultCorruptError(f"Campos obligatorios ausentes en la bóveda: {missing}")

    if data.get("version") != 1:
        raise VaultCorruptError(
            f"Versión de formato no soportada: {data.get('version')!r}. "
            "Sólo se admite la versión 1."
        )

    if data.get("kdf") != "argon2id":
        raise VaultCorruptError(
            f"Algoritmo KDF no soportado: {data.get('kdf')!r}. "
            "Sólo se admite 'argon2id'."
        )

    kdf_params = data.get("kdf_params", {})
    if not isinstance(kdf_params, dict):
        raise VaultCorruptError("kdf_params debe ser un objeto JSON.")

    missing_params = _REQUIRED_KDF_PARAMS - kdf_params.keys()
    if missing_params:
        raise VaultCorruptError(f"Parámetros KDF ausentes: {missing_params}")

    if kdf_params.get("hash_len") != 32:
        raise VaultCorruptError(
            f"kdf_params.hash_len debe ser 32, encontrado: {kdf_params.get('hash_len')!r}"
        )

    # Validar salt
    try:
        salt_bytes = base64.b64decode(data["salt"])
    except Exception as exc:
        raise VaultCorruptError(f"Campo 'salt' no es base64 válido: {exc}") from exc

    if len(salt_bytes) != 16:
        raise VaultCorruptError(
            f"El salt debe tener 16 bytes, encontrado: {len(salt_bytes)} bytes."
        )

    # Validar nonce
    try:
        nonce_bytes = base64.b64decode(data["nonce"])
    except Exception as exc:
        raise VaultCorruptError(f"Campo 'nonce' no es base64 válido: {exc}") from exc

    if len(nonce_bytes) != 12:
        raise VaultCorruptError(
            f"El nonce debe tener 12 bytes, encontrado: {len(nonce_bytes)} bytes."
        )

    return data


def save_vault_file(path: Path, data: dict) -> None:
    """Escribe el archivo de bóveda de forma atómica.

    Usa tempfile.NamedTemporaryFile + os.replace en el mismo directorio
    para garantizar atomicidad: el archivo de destino se reemplaza
    completamente o no se modifica (no puede quedar en estado parcial).

    Args:
        path: Ruta destino del archivo .vault.
        data: Dict con los datos del vault (ya cifrados).
    """
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)

    content = json.dumps(data, ensure_ascii=False, indent=2)

    # Crear el temporal en el mismo directorio para garantizar que os.replace
    # sea una operación atómica (mismo sistema de archivos).
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".vault.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
