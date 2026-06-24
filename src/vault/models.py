"""Modelos de datos del dominio — entidades de la bóveda.

Todos son dataclasses simples con serialización to_dict/from_dict.
NO contienen lógica de negocio; esa responsabilidad es de VaultService.

Constitución: Principio II — ninguna entidad abre conexiones de red.
              Principio VI — claves en bytearray para permitir zeroing.
"""
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class FolderRecord:
    """Carpeta organizadora de entradas en la bóveda."""
    id: str
    name: str

    @classmethod
    def create(cls, name: str) -> "FolderRecord":
        """Crea una nueva carpeta con UUID4 generado."""
        return cls(id=_new_uuid(), name=name)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, d: dict) -> "FolderRecord":
        return cls(id=d["id"], name=d["name"])


@dataclass
class EntryRecord:
    """Entrada de credenciales almacenada en la bóveda."""
    id: str
    title: str
    username: str
    password: str
    url: str
    notes: str
    folder_id: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        title: str,
        username: str = "",
        password: str = "",
        url: str = "",
        notes: str = "",
        folder_id: Optional[str] = None,
    ) -> "EntryRecord":
        """Crea una nueva entrada con UUID4 y timestamps actuales."""
        now = _now_iso()
        return cls(
            id=_new_uuid(),
            title=title,
            username=username,
            password=password,
            url=url,
            notes=notes,
            folder_id=folder_id,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "username": self.username,
            "password": self.password,
            "url": self.url,
            "notes": self.notes,
            "folder_id": self.folder_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EntryRecord":
        return cls(
            id=d["id"],
            title=d["title"],
            username=d.get("username", ""),
            password=d.get("password", ""),
            url=d.get("url", ""),
            notes=d.get("notes", ""),
            folder_id=d.get("folder_id"),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )


@dataclass
class VaultPayload:
    """Payload descifrado de la bóveda — NUNCA se almacena en disco."""
    folders: list  # list[FolderRecord]
    entries: list  # list[EntryRecord]

    def to_dict(self) -> dict:
        return {
            "folders": [f.to_dict() for f in self.folders],
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VaultPayload":
        return cls(
            folders=[FolderRecord.from_dict(f) for f in d.get("folders", [])],
            entries=[EntryRecord.from_dict(e) for e in d.get("entries", [])],
        )


@dataclass
class VaultSession:
    """Estado en memoria de una sesión de bóveda desbloqueada.

    NUNCA se serializa a disco. La clave derivada se almacena como bytearray
    para poder sobreescribirla con ceros al bloquear (zero_key).

    Atributos adicionales (internos, no expuestos en la API pública):
        salt_b64: Salt original de la bóveda, necesario para re-cifrar en _save().
        kdf_params: Parámetros KDF del archivo, necesarios para reconstruir el AAD.
    """
    derived_key: bytearray       # 32 bytes — NUNCA en disco
    vault_file_path: Path
    payload: VaultPayload
    salt_b64: str                # para reconstruir el envelope al guardar
    kdf_params: dict             # para reconstruir el AAD al guardar

    def zero_key(self) -> None:
        """Sobreescribe la clave derivada con ceros en memoria.

        Llama a esto ANTES de eliminar la referencia al VaultSession
        para minimizar el tiempo que la clave permanece en RAM.
        """
        for i in range(len(self.derived_key)):
            self.derived_key[i] = 0


# ── Configuración de usuario (T038) ──────────────────────────────────────────

# Ruta de configuración por defecto — directorio de usuario estándar XDG / macOS / Windows.
_DEFAULT_CONFIG_PATH = Path.home() / ".config" / "vault-manager" / "settings.json"

# Alias público para que app.py pueda importarlo (T039).
APP_CONFIG_PATH = _DEFAULT_CONFIG_PATH

# Límites permitidos por el diálogo de configuración (T039).
CLIPBOARD_TIMEOUT_MIN = 5
CLIPBOARD_TIMEOUT_MAX = 300
AUTO_LOCK_TIMEOUT_MIN = 60
AUTO_LOCK_TIMEOUT_MAX = 3600


@dataclass
class AppSettings:
    """Configuración de usuario no sensible, persistida como JSON.

    Atributos:
        clipboard_timeout_s: Segundos hasta borrar el portapapeles (FR-016, C-004).
        auto_lock_timeout_s: Segundos de inactividad antes del auto-bloqueo (FR-017).

    Refs: T038 (plan.md Phase 10); FR-016 (borrado portapapeles); FR-017 (auto-bloqueo).
    """
    clipboard_timeout_s: int = 20
    auto_lock_timeout_s: int = 300

    def to_dict(self) -> dict:
        return {
            "clipboard_timeout_s": self.clipboard_timeout_s,
            "auto_lock_timeout_s": self.auto_lock_timeout_s,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AppSettings":
        return cls(
            clipboard_timeout_s=int(d.get("clipboard_timeout_s", 20)),
            auto_lock_timeout_s=int(d.get("auto_lock_timeout_s", 300)),
        )


def load_settings(config_path: Path = _DEFAULT_CONFIG_PATH) -> "AppSettings":
    """Carga la configuración desde config_path.

    Si el archivo no existe o está corrupto devuelve los valores por defecto
    sin lanzar excepción — comportamiento silencioso y seguro.

    Refs: T038; la configuración es no sensible (no cifrada).

    Args:
        config_path: Ruta al archivo JSON de configuración.

    Returns:
        AppSettings con los valores leídos del archivo o los valores por defecto.
    """
    try:
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return AppSettings.from_dict(data)
    except Exception:  # JSON malformado, permisos, etc. — degradación silenciosa
        pass
    return AppSettings()


def save_settings(config_path: Path, settings: "AppSettings") -> None:
    """Persiste la configuración en config_path como JSON.

    Crea los directorios intermedios si no existen.
    La configuración es no sensible: sin cifrado.

    Refs: T038; Principio II — sin tráfico de red; datos locales no sensibles.

    Args:
        config_path: Ruta donde escribir el archivo JSON.
        settings:    AppSettings a persistir.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
