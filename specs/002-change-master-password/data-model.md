# Modelo de Datos: Cambiar Contraseña Maestra (Rotación)

**Feature**: `002-change-master-password`
**Date**: 2026-06-29
**Referencia**: [spec.md](spec.md) → Key Entities

---

## Resumen

Esta feature **no introduce entidades nuevas**. Modifica exclusivamente los **metadatos de
cifrado de la bóveda existente** (salt, nonce, AAD vinculada). El contenido lógico de entradas
y carpetas no cambia; solo cambia el cifrado que lo protege.

---

## Entidades afectadas

### VaultSession *(solo en memoria — nunca en disco)*

Objeto interno de `VaultService` que representa la sesión activa.

| Atributo | Tipo | Descripción | Cambio tras rotación |
|----------|------|-------------|----------------------|
| `derived_key` | `bytearray` | Clave AES-256 derivada de la maestra | **Reemplazada** por la nueva; la antigua se sobreescribe a ceros |
| `vault_file_path` | `Path` | Ruta al archivo de bóveda | Sin cambio |
| `payload` | `VaultPayload` | Entradas y carpetas en memoria | Sin cambio (solo re-cifrado) |
| `salt_b64` | `str` | Salt actual en base64 | **Reemplazado** por el nuevo salt |
| `kdf_params` | `dict` | Parámetros Argon2id | Sin cambio (FR-017: preservar) |

**Notas**:
- `derived_key` es `bytearray` (mutable) para permitir zeroing explícito.
- El zeroing de la clave antigua ocurre inmediatamente tras el commit atómico y antes de
  devolver el control al código de la UI (NFR-004).
- `VaultSession` no se persiste; los cambios de `salt_b64` y `derived_key` en memoria reflejan
  el nuevo estado de la bóveda en disco.

---

### Archivo de bóveda *(en disco — formato JSON cifrado)*

Estructura de los campos del archivo `.vault` tras una rotación exitosa:

| Campo | Tipo | Descripción | Cambio tras rotación |
|-------|------|-------------|----------------------|
| `version` | `int` | Versión del formato (actualmente `1`) | Sin cambio |
| `kdf` | `str` | Algoritmo KDF (`"argon2id"`) | Sin cambio |
| `kdf_params` | `dict` | Parámetros Argon2id (`time_cost`, `memory_cost`, `parallelism`, `hash_len`) | Sin cambio (FR-017) |
| `salt` | `str` | Salt en base64 (16 bytes) | **Nuevo valor** — salt aleatorio generado para esta rotación (NFR-001) |
| `nonce` | `str` | Nonce AES-GCM en base64 (12 bytes) | **Nuevo valor** — nonce nuevo para la nueva clave (FR-008) |
| `ciphertext` | `str` | Payload cifrado + tag GCM en base64 | **Re-cifrado** — mismo `VaultPayload`, nueva clave, nuevo nonce |

**AAD (datos adicionales autenticados)**:
Los campos `version`, `kdf`, `kdf_params` y `salt` (el **nuevo** salt) se autentican como AAD
en el re-cifrado. La AAD apunta siempre a los metadatos del archivo que la contiene; nunca a
metadatos de una versión anterior (NFR-003, FR-009).

---

### VaultPayload *(contenido lógico — no cambia)*

| Atributo | Tipo | Descripción | Cambio |
|----------|------|-------------|--------|
| `folders` | `list[FolderRecord]` | Carpetas organizadoras | Sin cambio |
| `entries` | `list[EntryRecord]` | Credenciales almacenadas | Sin cambio |

El JSON serializado de `VaultPayload` es idéntico antes y después de la rotación. Solo el
envelope que lo cifra (salt, nonce, clave) cambia.

---

## Transiciones de estado relevantes

```
Estado antes de rotar:
  disco:   { salt: S1, nonce: N1, kdf_params: P, ciphertext: C1(key1, N1, AAD(S1, P)) }
  memoria: VaultSession { derived_key: key1, salt_b64: S1, payload: PL }

── rotación (operación atómica) ──────────────────────────────────────────────

  1. Verificar: re-derivar desde current_password + S1 + P → key1' == key1 ✓
  2. Validar new_password: len ≥ 12, not identical to current_password
  3. Generar: S2 = random_salt()
  4. Derivar: key2 = Argon2id(new_password, S2, P)
  5. Serializar: plaintext = JSON(payload PL) [idéntico]
  6. Cifrar: N2 = random_nonce(); C2 = AES-GCM(plaintext, key2, N2, AAD(S2, P))
  7. Escribir temp file: { salt: S2, nonce: N2, kdf_params: P, ciphertext: C2 }
  8. COMMIT: os.replace(temp, vault_file)   ← punto de no retorno
  9. Actualizar sesión: derived_key → key2, salt_b64 → S2
  10. Zeroing: zero(key1), zero(key2 ref anterior si aplica)

Estado tras rotar:
  disco:   { salt: S2, nonce: N2, kdf_params: P, ciphertext: C2(key2, N2, AAD(S2, P)) }
  memoria: VaultSession { derived_key: key2, salt_b64: S2, payload: PL }

Invariante: S2 ≠ S1 (salt nuevo); N2 ≠ N1 (nonce nuevo); key1 ≠ key2 (distinta contraseña o mismo salt).
Garantía AAD: modificar S2, P o version en disco → fallo de tag GCM al descifrar.
```

---

## Reglas de validación previas al commit

| Regla | Origen | Mensaje de error |
|-------|--------|-----------------|
| `current_password` re-deriva correctamente → `key1'` == `_session.derived_key` | FR-003 | "Contraseña maestra actual incorrecta." |
| `new_password != current_password` | FR-018 | "La nueva contraseña no puede ser igual a la actual." |
| `len(new_password) >= 12` | FR-019 | "La nueva contraseña debe tener al menos 12 caracteres." |
| `new_password == confirmation` | FR-005 | "Las contraseñas no coinciden." |
| `new_password != ""` | FR-005 | "La nueva contraseña no puede estar vacía." |

**Orden de validación recomendado**: (1) vacío → (2) longitud → (3) confirmación → (4) identidad
→ (5) re-autenticación (costosa: Argon2id — solo si las validaciones baratas pasan).
