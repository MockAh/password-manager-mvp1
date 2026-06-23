# Contrato: Interfaz Pública de VaultService

**Feature**: `001-local-password-manager`
**Date**: 2026-06-17
**Módulo fuente**: `src/vault/service.py`

`VaultService` es la única puerta de entrada de la capa de UI y de los tests al estado de la
bóveda. Ningún componente externo llama directamente a `src/crypto/` ni accede a `VaultPayload`
sin pasar por este servicio.

---

## Contrato de la Clase VaultService

```python
class VaultService:
    """
    Servicio de bóveda. Expone la lógica de negocio a la capa UI y a los tests.
    No tiene dependencias de Tkinter ni de la capa de presentación.
    """

    # ── Ciclo de vida de la bóveda ─────────────────────────────────────────

    def create_vault(self, file_path: Path, master_password: str) -> None:
        """
        Crea una nueva bóveda vacía y la persiste cifrada en file_path.

        Precondiciones:
        - file_path no debe existir (lanza VaultAlreadyExistsError si existe).
        - master_password no debe estar vacío.

        Postcondiciones:
        - Archivo cifrado escrito en file_path (escritura atómica).
        - La sesión interna queda en estado DESBLOQUEADO.
        - Salt y nonce generados aleatoriamente; nunca reutilizados.
        """

    def unlock_vault(self, file_path: Path, master_password: str) -> None:
        """
        Abre y descifra la bóveda en file_path usando master_password.

        Lanza:
        - WrongPasswordError si la contraseña es incorrecta (fallo de autenticación GCM).
        - VaultCorruptError si el archivo está corrupto o malformado.
        - FileNotFoundError si file_path no existe.

        Postcondiciones:
        - La sesión interna queda en estado DESBLOQUEADO.
        - La clave derivada existe en memoria; nunca en disco.
        """

    def lock_vault(self) -> None:
        """
        Bloquea la bóveda activa:
        - Sobreescribe la clave derivada con ceros.
        - Cancela el timer de portapapeles y limpia el portapapeles.
        - Descarta el payload descifrado de memoria.
        - La sesión queda en estado BLOQUEADO.

        No-op si ya está bloqueada.
        """

    @property
    def is_unlocked(self) -> bool:
        """True si hay una sesión activa desbloqueada."""

    # ── Gestión de entradas ────────────────────────────────────────────────

    def get_entries(self, folder_id: str | None = None) -> list[EntryRecord]:
        """
        Devuelve las entradas de la bóveda.
        Si folder_id es None, devuelve todas las entradas.
        Si folder_id es una cadena vacía "" o el valor sentinel NO_FOLDER,
        devuelve las entradas sin carpeta asignada.
        Si folder_id es un UUID válido, devuelve las entradas de esa carpeta.
        Lanza VaultLockedError si la bóveda está bloqueada.
        """

    def search_entries(self, query: str) -> list[EntryRecord]:
        """
        Filtra las entradas cuyo title o username contiene query
        (comparación case-insensitive, subcadena).
        Devuelve lista vacía si no hay coincidencias.
        Lanza VaultLockedError si la bóveda está bloqueada.
        """

    def add_entry(self, title: str, username: str, password: str,
                  url: str = "", notes: str = "",
                  folder_id: str | None = None) -> EntryRecord:
        """
        Crea una nueva entrada y guarda el vault.
        Lanza ValueError si title está vacío.
        Lanza FolderNotFoundError si folder_id no corresponde a una carpeta existente.
        Devuelve el EntryRecord creado.
        """

    def update_entry(self, entry_id: str, **fields) -> EntryRecord:
        """
        Actualiza los campos especificados en **fields de la entrada con entry_id.
        Campos actualizables: title, username, password, url, notes, folder_id.
        Actualiza updated_at automáticamente.
        Lanza EntryNotFoundError si entry_id no existe.
        Guarda el vault tras la actualización.
        """

    def delete_entry(self, entry_id: str) -> None:
        """
        Elimina la entrada con entry_id.
        Lanza EntryNotFoundError si entry_id no existe.
        Guarda el vault tras la eliminación.
        """

    # ── Gestión de carpetas ────────────────────────────────────────────────

    def get_folders(self) -> list[FolderRecord]:
        """Devuelve todas las carpetas. Lanza VaultLockedError si bloqueada."""

    def add_folder(self, name: str) -> FolderRecord:
        """
        Crea una nueva carpeta con el nombre dado.
        Lanza ValueError si name está vacío o supera 255 caracteres.
        Lanza DuplicateFolderNameError si ya existe una carpeta con ese nombre.
        """

    def delete_folder(self, folder_id: str) -> int:
        """
        Elimina la carpeta. Las entradas asignadas a ella pasan a folder_id = None.
        Lanza FolderNotFoundError si folder_id no existe.
        Devuelve el número de entradas que pasaron a "Sin carpeta".
        """

    # ── Actividad (para auto-bloqueo) ──────────────────────────────────────

    def record_activity(self) -> None:
        """
        Registra actividad del usuario (actualiza last_activity_at).
        La UI llama a este método en cada interacción (tecla, clic, scroll).
        """
```

---

## Excepciones del Dominio

Todas se importan desde `src/vault/service.py`:

| Excepción | Cuándo se lanza |
|-----------|-----------------|
| `VaultLockedError` | Operación sobre vault bloqueada |
| `VaultAlreadyExistsError` | `create_vault` con `file_path` ya existente |
| `WrongPasswordError` | Contraseña maestra incorrecta (fallo GCM `InvalidTag`) |
| `VaultCorruptError` | Archivo malformado o corrupto (JSON inválido, campos faltantes, salt/nonce con tamaño incorrecto) |
| `EntryNotFoundError` | `entry_id` inexistente en `update_entry` / `delete_entry` |
| `FolderNotFoundError` | `folder_id` inexistente en operaciones de carpeta |
| `DuplicateFolderNameError` | Nombre de carpeta ya existe |

---

## Contrato del Módulo Criptográfico

**Módulo**: `src/crypto/vault_cipher.py`

```python
def build_aad(version: int, kdf: str, kdf_params: dict, salt_b64: str) -> bytes:
    """
    Construye los datos adicionales autenticados (AAD) para AES-256-GCM.
    Serializa los campos del envelope como JSON canónico (sort_keys=True, UTF-8).

    Motivo: impedir ataques de downgrade de parámetros KDF. Si un atacante reduce
    kdf_params.memory_cost para facilitar la fuerza bruta, el AAD calculado al
    descifrar no coincidirá con el usado al cifrar, causando InvalidTag inmediato.

    El resultado es idéntico al cifrar y al descifrar siempre que los campos del
    envelope no hayan sido modificados.
    """

def encrypt(plaintext: bytes, key: bytes, envelope_meta: dict) -> tuple[bytes, bytes]:
    """
    Cifra plaintext con AES-256-GCM.

    Parámetros:
    - plaintext: payload JSON de VaultPayload codificado en UTF-8.
    - key: 32 bytes derivados por Argon2id.
    - envelope_meta: dict con version, kdf, kdf_params, salt (base64) — usados como AAD.

    Proceso:
    1. Genera nonce de 12 bytes con os.urandom(12).
    2. Construye AAD = build_aad(envelope_meta).
    3. Cifra con AESGCM(key).encrypt(nonce, plaintext, aad).

    Devuelve: (nonce: bytes, ciphertext_with_tag: bytes)
    """

def decrypt(ciphertext_with_tag: bytes, nonce: bytes, key: bytes,
            envelope_meta: dict) -> bytes:
    """
    Descifra y verifica la autenticidad del ciphertext.

    Proceso:
    1. Construye AAD = build_aad(envelope_meta) con los mismos campos del envelope.
    2. Descifra con AESGCM(key).decrypt(nonce, ciphertext_with_tag, aad).

    Lanza cryptography.exceptions.InvalidTag si:
    - La contraseña maestra es incorrecta (clave derivada diferente).
    - El ciphertext, nonce o cualquier campo del envelope en AAD ha sido modificado.

    Devuelve: plaintext bytes (payload JSON de VaultPayload).
    """
```

---

## Contrato del Generador de Contraseñas

**Módulo**: `src/generator/password_generator.py`

```python
def generate_password(
    length: int,
    use_uppercase: bool = True,
    use_lowercase: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
) -> str:
    """
    Genera una contraseña aleatoria usando secrets.choice (CSPRNG).

    Precondiciones:
    - 8 <= length <= 128
    - Al menos uno de los flags use_* debe ser True.

    Garantías:
    - El resultado contiene solo caracteres de los conjuntos habilitados.
    - len(resultado) == length.
    - Usa secrets.choice (criptográficamente seguro); nunca random.choice.

    Lanza ValueError si length está fuera del rango o ningún charset está habilitado.
    """
```

---

## Contrato del Portapapeles

**Módulo**: `src/ui/clipboard.py`

```python
def copy_to_clipboard(root: tk.Tk, value: str, clear_after_s: int = 20) -> None:
    """
    Copia value al portapapeles del sistema operativo.
    Programa la limpieza automática del portapapeles tras clear_after_s segundos.
    Si había un timer previo activo, lo cancela antes de programar el nuevo.

    Postcondiciones:
    - El portapapeles contiene value inmediatamente.
    - Tras clear_after_s segundos, el portapapeles se limpia (clipboard_clear()).
    """

def cancel_clipboard_timer() -> None:
    """
    Cancela el timer de limpieza activo y limpia el portapapeles inmediatamente.
    Llamado al bloquear la bóveda (FR-022).
    """
```
