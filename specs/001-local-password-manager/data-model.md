# Data Model: Gestor de Contraseñas Local y Offline

**Feature**: `001-local-password-manager`
**Date**: 2026-06-17
**Source**: [spec.md — Key Entities](spec.md) + [research.md](research.md)

---

## Entidades

### Vault (Bóveda — en disco)

Representa el archivo cifrado en disco. Solo los campos no sensibles se almacenan en texto plano.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `version` | `int` | ✅ | Versión del formato del archivo (v1 = `1`) |
| `kdf` | `str` | ✅ | Identificador del algoritmo KDF (`"argon2id"`) |
| `kdf_params` | `object` | ✅ | Parámetros de la KDF (ver sub-tabla) |
| `salt` | `str` | ✅ | Salt criptográfico en base64 (16 bytes / 128 bits) |
| `nonce` | `str` | ✅ | Nonce AES-GCM en base64 (12 bytes / 96 bits) |
| `ciphertext` | `str` | ✅ | Payload cifrado + tag GCM en base64 |

**kdf_params (Argon2id)**:

| Campo | Tipo | Valor v1 | Descripción |
|-------|------|----------|-------------|
| `time_cost` | `int` | `3` | Número de iteraciones |
| `memory_cost` | `int` | `65536` | Coste de memoria en KiB (64 MB) |
| `parallelism` | `int` | `1` | Hilos de paralelismo |
| `hash_len` | `int` | `32` | Longitud del hash derivado en bytes (256 bits) |

**Reglas de validación**:
- `salt` DEBE tener exactamente 16 bytes una vez decodificado.
- `nonce` DEBE tener exactamente 12 bytes una vez decodificado.
- `kdf_params.hash_len` DEBE ser 32 (tamaño de clave AES-256).
- El `ciphertext` incluye el authentication tag de 16 bytes al final (convención de `cryptography`).
- Si algún campo de validación falla al abrir el archivo, la apertura se rechaza con error claro.

---

### VaultPayload (Payload descifrado — solo en memoria)

El contenido del vault después del descifrado. Nunca se escribe en disco en texto plano.
Serializado como JSON para cifrar y almacenar.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `folders` | `list[FolderRecord]` | Lista de carpetas (puede estar vacía) |
| `entries` | `list[EntryRecord]` | Lista de entradas de credenciales |

---

### FolderRecord (Carpeta)

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `id` | `str` (UUID4) | ✅ | Identificador único inmutable |
| `name` | `str` | ✅ | Nombre de la carpeta; no vacío; máx. 255 caracteres |

**Reglas**:
- Las carpetas son planas en v1: no hay carpetas padre ni anidamiento.
- Al eliminar una carpeta, todas las entradas con `folder_id` igual al id de la carpeta pasan a
  `folder_id = null`. Las entradas nunca se eliminan en cascada.
- Dos carpetas no pueden tener el mismo nombre (validación en `VaultService`).

---

### EntryRecord (Entrada de credencial)

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `id` | `str` (UUID4) | ✅ | Identificador único inmutable |
| `title` | `str` | ✅ | Nombre del sitio o URL; no vacío; máx. 512 caracteres |
| `username` | `str` | ✅ | Nombre de usuario; puede estar vacío |
| `password` | `str` | ✅ | Contraseña; puede estar vacía |
| `url` | `str` | ❌ | URL del servicio; puede estar vacía |
| `notes` | `str` | ❌ | Notas libres; puede estar vacía; sin límite de longitud |
| `folder_id` | `str` \| `null` | ❌ | UUID de la carpeta asignada; `null` = sin carpeta |
| `created_at` | `str` (ISO 8601 UTC) | ✅ | Fecha y hora de creación; no modificable |
| `updated_at` | `str` (ISO 8601 UTC) | ✅ | Fecha y hora de la última modificación |

**Reglas**:
- `id` se genera en la creación y nunca se modifica.
- `created_at` se fija en la creación y nunca se modifica.
- `updated_at` se actualiza en cada edición de cualquier campo.
- `folder_id` DEBE corresponder al `id` de una `FolderRecord` existente, o ser `null`.
- Al buscar, se filtra por subcadena (case-insensitive) en `title` y `username`.

---

### VaultSession (Sesión activa — solo en memoria, nunca en disco)

Estado en memoria de la bóveda desbloqueada. Se descarta completamente al bloquear.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `derived_key` | `bytearray` (32 bytes) | Clave AES-256 derivada con Argon2id; sobreescrita con ceros al bloquear |
| `vault_file_path` | `Path` | Ruta al archivo de bóveda en disco |
| `payload` | `VaultPayload` | Datos descifrados en memoria |
| `last_activity_at` | `datetime` | Marca de tiempo de la última interacción del usuario; usada por el timer de auto-bloqueo |
| `clipboard_timer` | `threading.Timer \| None` | Timer activo de borrado del portapapeles; se cancela al bloquear |

**Reglas de ciclo de vida**:
- `VaultSession` se crea al desbloquear y se destruye al bloquear.
- Al destruir: `derived_key[:] = b'\x00' * 32`, se cancela `clipboard_timer`, se limpia el portapapeles.
- `last_activity_at` se actualiza con cada interacción del usuario en la UI.

---

## Relaciones entre Entidades

```
VaultFile (disco)
  └─ cifra/descifra ──→ VaultPayload (memoria)
                             ├─ folders: [FolderRecord, ...]
                             └─ entries: [EntryRecord, ...]
                                            └─ folder_id ──→ FolderRecord.id (o null)

VaultSession (memoria)
  ├─ derived_key  (32 bytes, Argon2id)
  ├─ vault_file_path
  └─ payload ──→ VaultPayload
```

---

## Transiciones de Estado del Sistema

```
[Sin bóveda]
    │ Crear nueva bóveda
    ▼
[Bóveda bloqueada]
    │ Contraseña maestra correcta
    ▼
[Bóveda desbloqueada] ──── Inactividad ≥ 5 min ──→ [Bóveda bloqueada]
    │                  ──── Bloqueo manual    ──→ [Bóveda bloqueada]
    │
    ├─ CRUD entradas / carpetas
    ├─ Búsqueda en tiempo real
    ├─ Generar contraseña
    └─ Copiar al portapapeles (timer 20 s)
```

---

## Serialización del Payload (JSON interno)

```json
{
  "folders": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Trabajo"
    }
  ],
  "entries": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "title": "GitHub",
      "username": "usuario@ejemplo.com",
      "password": "s3cr3t!",
      "url": "https://github.com",
      "notes": "",
      "folder_id": "550e8400-e29b-41d4-a716-446655440001",
      "created_at": "2026-06-17T10:00:00Z",
      "updated_at": "2026-06-17T10:05:00Z"
    }
  ]
}
```
