"""Servicio de bóveda — capa de negocio principal.

Responsabilidades (US1–US2, Fases 3–4):
  - Crear una bóveda nueva (create_vault).
  - Desbloquear una bóveda existente (unlock_vault).
  - Bloquear la sesión activa (lock_vault).
  - Auto-bloqueo por inactividad con threading.Timer.
  - CRUD de entradas: get_entries, add_entry, update_entry, delete_entry.

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
    EntryNotFoundError,
    FolderNotFoundError,
)
from vault.models import EntryRecord, VaultPayload, VaultSession

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

# Sentinel para get_entries: devuelve entradas sin carpeta asignada.
# Corresponde al contrato vault-service-interface.md → get_entries(folder_id="").
NO_FOLDER: str = ""


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

    # ── Gestión de entradas (US2) ─────────────────────────────────────────────

    def get_entries(self, folder_id: Optional[str] = None) -> list:
        """Devuelve entradas de la bóveda según el filtro de carpeta.

        Contrato (vault-service-interface.md):
          - folder_id is None  → todas las entradas (sin filtro).
          - folder_id == ""    → entradas sin carpeta asignada (folder_id=None en modelo).
          - folder_id == uuid  → entradas asignadas a esa carpeta.

        Refs: FR-010 (listado de entradas), US2 Acceptance Scenario 5.

        Raises:
            VaultLockedError: si la bóveda está bloqueada.
        """
        session = self._require_unlocked()
        entries = session.payload.entries
        if folder_id is None:
            return list(entries)
        if folder_id == NO_FOLDER:
            return [e for e in entries if e.folder_id is None]
        return [e for e in entries if e.folder_id == folder_id]

    def add_entry(
        self,
        title: str,
        username: str = "",
        password: str = "",
        url: str = "",
        notes: str = "",
        folder_id: Optional[str] = None,
    ) -> "EntryRecord":
        """Crea una nueva entrada y persiste la bóveda.

        Genera UUID4 y timestamps ISO-8601 UTC (data-model.md → EntryRecord.create).
        Guarda el vault cifrado tras la creación.

        Refs: FR-010 (añadir entrada), US2 Acceptance Scenario 1.

        Raises:
            ValueError: si title está vacío (data-model.md: title no vacío).
            FolderNotFoundError: si folder_id no corresponde a carpeta existente.
            VaultLockedError: si la bóveda está bloqueada.
        """
        session = self._require_unlocked()
        if not title:
            raise ValueError("El título de la entrada no puede estar vacío.")
        if folder_id is not None:
            known_ids = {f.id for f in session.payload.folders}
            if folder_id not in known_ids:
                raise FolderNotFoundError(
                    f"No existe ninguna carpeta con id: {folder_id}"
                )
        entry = EntryRecord.create(
            title=title,
            username=username,
            password=password,
            url=url,
            notes=notes,
            folder_id=folder_id,
        )
        session.payload.entries.append(entry)
        self._save()
        return entry

    def update_entry(self, entry_id: str, **fields) -> "EntryRecord":
        """Actualiza los campos indicados de una entrada y persiste la bóveda.

        Campos actualizables: title, username, password, url, notes, folder_id.
        Actualiza updated_at automáticamente (data-model.md).

        Refs: FR-010 (editar entrada), US2 Acceptance Scenario 2.

        Raises:
            EntryNotFoundError: si entry_id no existe.
            FolderNotFoundError: si el folder_id proporcionado no existe.
            VaultLockedError: si la bóveda está bloqueada.
        """
        from datetime import datetime, timezone
        session = self._require_unlocked()
        entry = self._find_entry(session, entry_id)

        allowed = {"title", "username", "password", "url", "notes", "folder_id"}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "folder_id" and value is not None:
                known_ids = {f.id for f in session.payload.folders}
                if value not in known_ids:
                    raise FolderNotFoundError(
                        f"No existe ninguna carpeta con id: {value}"
                    )
            setattr(entry, key, value)

        entry.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._save()
        return entry

    def delete_entry(self, entry_id: str) -> None:
        """Elimina la entrada con entry_id y persiste la bóveda.

        Refs: FR-010 (eliminar entrada), US2 Acceptance Scenarios 3–4.

        Raises:
            EntryNotFoundError: si entry_id no existe.
            VaultLockedError: si la bóveda está bloqueada.
        """
        session = self._require_unlocked()
        entry = self._find_entry(session, entry_id)
        session.payload.entries.remove(entry)
        self._save()

    # ── Búsqueda en tiempo real (US3) ─────────────────────────────────────────

    def search_entries(self, query: str) -> list:
        """Filtra entradas por subcadena case-insensitive en title o username.

        Contrato (contracts/vault-service-interface.md → search_entries):
          - Comparación case-insensitive, coincidencia por subcadena.
          - query vacío ("") coincide con todas las entradas.
          - Devuelve lista vacía si no hay coincidencias.

        Refs: FR-013 (búsqueda en tiempo real), SC-003 (≤ 100 ms / 500 entradas),
              US3 Acceptance Scenarios 1–3.

        Raises:
            VaultLockedError: si la bóveda está bloqueada.
        """
        session = self._require_unlocked()
        needle = query.casefold()
        return [
            e for e in session.payload.entries
            if needle in e.title.casefold() or needle in e.username.casefold()
        ]

    # ── Ayudantes internos ────────────────────────────────────────────────────

    def _find_entry(self, session: "VaultSession", entry_id: str) -> "EntryRecord":
        """Localiza una entrada por ID o lanza EntryNotFoundError."""
        for entry in session.payload.entries:
            if entry.id == entry_id:
                return entry
        raise EntryNotFoundError(f"No existe ninguna entrada con id: {entry_id}")

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
