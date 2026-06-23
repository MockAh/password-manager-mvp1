"""Servicio de bóveda — capa de negocio principal.

Responsabilidades (US1, Fase 3):
  - Crear una bóveda nueva (create_vault).
  - Desbloquear una bóveda existente (unlock_vault).
  - Bloquear la sesión activa (lock_vault).
  - Auto-bloqueo por inactividad con threading.Timer.

Constitución:
  Principio I — clave derivada nunca en disco; salt único por bóveda.
  Principio III — AES-256-GCM con AAD; Argon2id KDF.
  Principio IV — no hay recuperación de contraseña maestra.
  Principio VI — zeroing de clave derivada al bloquear.
"""
import base64
import json
import threading
from pathlib import Path
from typing import Callable, Optional

from cryptography.exceptions import InvalidTag

from crypto.kdf import (
    ARGON2_HASH_LEN,
    ARGON2_MEMORY_COST,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    derive_key,
    generate_salt,
)
from crypto.vault_cipher import decrypt, encrypt
from vault import repository
from vault.exceptions import (
    VaultAlreadyExistsError,
    VaultCorruptError,
    VaultLockedError,
    WrongPasswordError,
)
from vault.models import VaultPayload, VaultSession

# ── Constantes de formato ─────────────────────────────────────────────────────

VAULT_FORMAT_VERSION = 1
VAULT_KDF = "argon2id"
DEFAULT_KDF_PARAMS = {
    "time_cost": ARGON2_TIME_COST,
    "memory_cost": ARGON2_MEMORY_COST,
    "parallelism": ARGON2_PARALLELISM,
    "hash_len": ARGON2_HASH_LEN,
}
DEFAULT_AUTO_LOCK_TIMEOUT_S = 300  # 5 minutos — FR-017


class VaultService:
    """Servicio principal de gestión de la bóveda local.

    Una sola instancia por aplicación. Sólo admite una bóveda abierta
    simultáneamente (Clarificación C-002).
    """

    def __init__(
        self,
        auto_lock_timeout_s: int = DEFAULT_AUTO_LOCK_TIMEOUT_S,
        on_auto_lock: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Args:
            auto_lock_timeout_s: Segundos de inactividad antes del auto-bloqueo.
                                 0 para desactivar (útil en tests).
            on_auto_lock: Callback invocado en el hilo del Timer tras el auto-bloqueo.
                          Úsalo para actualizar la UI (p.ej. navegar a UnlockView).
        """
        self._session: Optional[VaultSession] = None
        self._auto_lock_timeout_s = auto_lock_timeout_s
        self._on_auto_lock = on_auto_lock
        self._inactivity_timer: Optional[threading.Timer] = None

    # ── Ciclo de vida de la bóveda ────────────────────────────────────────────

    def create_vault(self, file_path: Path, master_password: str) -> None:
        """Crea una nueva bóveda vacía, cifrada con master_password.

        Genera un salt único, deriva la clave con Argon2id y cifra un
        VaultPayload vacío con AES-256-GCM. La sesión queda desbloqueada.

        Args:
            file_path: Ruta donde crear el archivo .vault.
            master_password: Contraseña maestra elegida por el usuario.

        Raises:
            VaultAlreadyExistsError: Si ya existe un archivo en file_path.
            ValueError: Si master_password está vacío.
        """
        if file_path.exists():
            raise VaultAlreadyExistsError(
                f"Ya existe un archivo en: {file_path}"
            )
        if not master_password:
            raise ValueError("La contraseña maestra no puede estar vacía.")

        salt = generate_salt()
        salt_b64 = base64.b64encode(salt).decode("ascii")
        kdf_params = dict(DEFAULT_KDF_PARAMS)

        envelope_meta = {
            "version": VAULT_FORMAT_VERSION,
            "kdf": VAULT_KDF,
            "kdf_params": kdf_params,
            "salt": salt_b64,
        }

        key = derive_key(master_password, salt)
        try:
            payload = VaultPayload(folders=[], entries=[])
            plaintext = json.dumps(
                payload.to_dict(), ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            nonce, ciphertext_with_tag = encrypt(plaintext, key, envelope_meta)
        except Exception:
            # Zeroing preventivo si falla el cifrado (no debería ocurrir)
            for i in range(len(key)):
                key[i] = 0
            raise

        nonce_b64 = base64.b64encode(nonce).decode("ascii")
        ct_b64 = base64.b64encode(ciphertext_with_tag).decode("ascii")

        vault_data = {
            **envelope_meta,
            "nonce": nonce_b64,
            "ciphertext": ct_b64,
        }
        repository.save_vault_file(file_path, vault_data)

        # Si llegamos aquí, el vault está en disco; establecer sesión desbloqueada
        self._cancel_inactivity_timer()
        self._session = VaultSession(
            derived_key=key,
            vault_file_path=file_path,
            payload=payload,
            salt_b64=salt_b64,
            kdf_params=kdf_params,
        )
        self._start_inactivity_timer()

    def unlock_vault(self, file_path: Path, master_password: str) -> None:
        """Desbloquea una bóveda existente verificando la contraseña.

        Carga el archivo, deriva la clave con los parámetros del archivo
        y descifra el payload. Si ya hay una sesión abierta, se bloquea primero.

        Args:
            file_path: Ruta al archivo .vault existente.
            master_password: Contraseña maestra del usuario.

        Raises:
            VaultCorruptError: Si el archivo está malformado.
            WrongPasswordError: Si la contraseña es incorrecta o el archivo
                                ha sido manipulado (fallo de tag GCM).
        """
        # Bloquear sesión anterior si existe
        if self._session is not None:
            self.lock_vault()

        vault_data = repository.load_vault_file(file_path)

        salt_b64: str = vault_data["salt"]
        nonce_b64: str = vault_data["nonce"]
        ct_b64: str = vault_data["ciphertext"]
        kdf_params: dict = vault_data["kdf_params"]

        salt = base64.b64decode(salt_b64)
        nonce = base64.b64decode(nonce_b64)
        ciphertext_with_tag = base64.b64decode(ct_b64)

        envelope_meta = {
            "version": vault_data["version"],
            "kdf": vault_data["kdf"],
            "kdf_params": kdf_params,
            "salt": salt_b64,
        }

        key = derive_key(master_password, salt)
        try:
            plaintext = decrypt(ciphertext_with_tag, nonce, key, envelope_meta)
        except InvalidTag:
            for i in range(len(key)):
                key[i] = 0
            raise WrongPasswordError(
                "Contraseña maestra incorrecta o datos de la bóveda manipulados."
            )

        try:
            payload_dict = json.loads(plaintext.decode("utf-8"))
            payload = VaultPayload.from_dict(payload_dict)
        except Exception as exc:
            for i in range(len(key)):
                key[i] = 0
            raise VaultCorruptError(
                f"El payload descifrado no es JSON válido: {exc}"
            ) from exc

        self._cancel_inactivity_timer()
        self._session = VaultSession(
            derived_key=key,
            vault_file_path=file_path,
            payload=payload,
            salt_b64=salt_b64,
            kdf_params=kdf_params,
        )
        self._start_inactivity_timer()

    def lock_vault(self) -> None:
        """Bloquea la bóveda y zeroza la clave derivada de la memoria.

        Idempotente: no lanza excepción si la bóveda ya está bloqueada.
        """
        self._cancel_inactivity_timer()
        if self._session is not None:
            self._session.zero_key()
            self._session = None

    @property
    def is_unlocked(self) -> bool:
        """True si hay una sesión activa (bóveda desbloqueada)."""
        return self._session is not None

    # ── Gestión de actividad / auto-bloqueo ───────────────────────────────────

    def record_activity(self) -> None:
        """Reinicia el temporizador de inactividad.

        Llamar desde la UI en cualquier interacción del usuario (FR-017).
        """
        if self._session is not None:
            self._cancel_inactivity_timer()
            self._start_inactivity_timer()

    def _start_inactivity_timer(self) -> None:
        if self._auto_lock_timeout_s > 0:
            self._inactivity_timer = threading.Timer(
                self._auto_lock_timeout_s,
                self._auto_lock_triggered,
            )
            self._inactivity_timer.daemon = True
            self._inactivity_timer.start()

    def _cancel_inactivity_timer(self) -> None:
        if self._inactivity_timer is not None:
            self._inactivity_timer.cancel()
            self._inactivity_timer = None

    def _auto_lock_triggered(self) -> None:
        """Callback del Timer — se ejecuta en el hilo del Timer."""
        self.lock_vault()
        if self._on_auto_lock is not None:
            self._on_auto_lock()

    # ── Ayudantes internos ────────────────────────────────────────────────────

    def _require_unlocked(self) -> VaultSession:
        """Devuelve la sesión activa o lanza VaultLockedError."""
        if self._session is None:
            raise VaultLockedError("La bóveda está bloqueada.")
        return self._session

    def _save(self) -> None:
        """Recifra el payload actual y lo escribe atómicamente en disco.

        Genera un nonce fresco en cada llamada (requisito de seguridad:
        nunca reusar un nonce con la misma clave).
        """
        session = self._require_unlocked()

        plaintext = json.dumps(
            session.payload.to_dict(), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

        envelope_meta = {
            "version": VAULT_FORMAT_VERSION,
            "kdf": VAULT_KDF,
            "kdf_params": session.kdf_params,
            "salt": session.salt_b64,
        }

        nonce, ciphertext_with_tag = encrypt(plaintext, session.derived_key, envelope_meta)

        vault_data = {
            **envelope_meta,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext_with_tag).decode("ascii"),
        }
        repository.save_vault_file(session.vault_file_path, vault_data)
