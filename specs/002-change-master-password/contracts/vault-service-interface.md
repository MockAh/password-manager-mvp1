# Contrato: change_master_password — VaultService

**Feature**: `002-change-master-password`
**Date**: 2026-06-29
**Módulo fuente**: `src/vault/service.py`
**Extiende**: `specs/001-local-password-manager/contracts/vault-service-interface.md`

---

## Método nuevo: `change_master_password`

```python
def change_master_password(
    self,
    current_password: str,
    new_password: str,
) -> None:
    """
    Rota la contraseña maestra de la bóveda abierta.

    Verifica la contraseña actual, genera un salt nuevo, deriva una llave nueva
    con Argon2id, re-cifra el payload completo con AES-256-GCM (nonce nuevo,
    AAD re-vinculada) y persiste el resultado de forma atómica.

    Precondiciones:
    - La bóveda DEBE estar desbloqueada (lanza VaultLockedError si no).
    - current_password DEBE coincidir con la contraseña maestra actual
      (lanza WrongPasswordError si no).
    - new_password NO DEBE ser idéntico a current_password
      (lanza ValueError("identical") si son iguales).
    - len(new_password) >= 12
      (lanza ValueError("too_short") si es más corta).

    Postcondiciones (tras retorno sin excepción):
    - El archivo de bóveda en disco contiene un salt NUEVO (distinto al anterior),
      un nonce NUEVO, y el payload re-cifrado bajo la llave derivada de new_password.
    - Los metadatos (version, kdf, kdf_params, nuevo salt) están autenticados como
      AAD — modificarlos causa fallo de descifrado (NFR-003).
    - Los parámetros KDF (time_cost, memory_cost, parallelism, hash_len) son
      idénticos a los de la bóveda anterior (FR-017).
    - La sesión permanece DESBLOQUEADA con la llave nueva en memoria (FR-016).
    - La llave antigua y cualquier referencia a current_password / new_password
      en bytearray están sobreescritas a ceros (NFR-004).
    - No existe ningún archivo temporal residual en el directorio de la bóveda
      (NFR-005 / FR-012).
    - No existe ninguna copia del archivo descifrable con current_password
      más allá del estado pre-commit (NFR-005).

    Semántica de atomicidad (NFR-002):
    - Antes del commit (os.replace): el archivo original permanece intacto.
      Una interrupción en este punto deja la bóveda descifrable con la
      contraseña ANTERIOR.
    - Tras el commit (os.replace completo): el archivo nuevo está en disco.
      Una interrupción en este punto deja la bóveda descifrable con la
      contraseña NUEVA.
    - En ningún caso puede el archivo quedar en estado parcialmente escrito.

    Errores seguros (NFR-007):
    - WrongPasswordError: contraseña actual incorrecta. Mensaje específico
      en este contexto (bóveda ya abierta); no filtrable como "archivo dañado"
      porque el atacante ya ve la bóveda desbloqueada. El archivo no se toca.
    - VaultLockedError: se intenta rotar sin bóveda abierta.
    - ValueError: validación de new_password (vacío, muy corta, idéntica).
      El archivo no se toca.
    - OSError / IOError: fallo de escritura en disco. El archivo temporal se
      elimina; el original permanece intacto.

    Raises:
        VaultLockedError: Si la bóveda no está desbloqueada.
        WrongPasswordError: Si current_password no coincide con la maestra actual.
        ValueError: Si new_password es vacío, tiene < 12 caracteres, o es
                    idéntico a current_password.
        OSError: Si falla la escritura atómica en disco.
    """
```

---

## Métodos nuevos de gestión del auto-bloqueo

```python
def suspend_auto_lock(self) -> None:
    """
    Suspende el temporizador de auto-bloqueo por inactividad.

    El temporizador se cancela; la sesión permanece abierta.
    Llamar antes de iniciar la operación de rotación (FR-021).
    No-op si el auto-bloqueo está desactivado (timeout == 0).
    No-op si la bóveda está bloqueada.
    """

def resume_auto_lock(self) -> None:
    """
    Reanuda el temporizador de auto-bloqueo desde cero.

    Llamar al completar la operación de rotación (con éxito o fallo).
    Equivale a un reset del temporizador de inactividad.
    No-op si el auto-bloqueo está desactivado (timeout == 0).
    No-op si la bóveda está bloqueada.
    """
```

---

## Restricciones de la interfaz

| Propiedad | Valor |
|-----------|-------|
| Acceso requerido | Bóveda **desbloqueada** |
| Efectos colaterales en disco | Reemplazo atómico del archivo de bóveda (único efecto) |
| Estado en memoria post-llamada | Sesión abierta con llave **nueva**; llave antigua a ceros |
| Thread-safety | **No garantizado** — llamar desde hilo de fondo; UI updates vía `after(0, ...)` |
| Operaciones de red | **Ninguna** — 100 % offline (Principio II constitución) |
| Primitivas criptográficas usadas | Solo las ya existentes: `kdf.derive_key`, `kdf.generate_salt`, `vault_cipher.encrypt` |

---

## Secuencia de ejecución interna (contrato de comportamiento)

```
change_master_password(current_password, new_password):

  1. _require_unlocked()                            # VaultLockedError si bloqueada
  2. Validar new_password vacío                     # ValueError
  3. Validar len(new_password) >= 12                # ValueError("too_short")
  4. [Comparación de identidad — ver §siguiente]
  5. key_candidate = derive_key(current_password, session.salt)
  6. hmac.compare_digest(key_candidate, session.derived_key)  # WrongPasswordError si falla
  7. zero(key_candidate)
  8. new_salt = generate_salt()                     # NFR-001: salt nuevo
  9. new_key = derive_key(new_password, new_salt)   # FR-006 + FR-017: mismos kdf_params
  10. new_envelope_meta = { version, kdf, kdf_params, salt: new_salt_b64 }
  11. plaintext = JSON(session.payload)
  12. new_nonce, ciphertext = encrypt(plaintext, new_key, new_envelope_meta)  # FR-008, FR-009
  13. vault_data = { **new_envelope_meta, nonce: new_nonce_b64, ciphertext: ct_b64 }
  14. repository.save_vault_file(session.vault_file_path, vault_data)  # NFR-002: atómico
  15. zero(session.derived_key)                     # NFR-004: limpiar llave antigua
  16. session.derived_key = new_key                # FR-016: sesión con llave nueva
  17. session.salt_b64 = new_salt_b64
  # new_password y current_password se liberan al salir del scope
```

**Nota sobre comparación de identidad (paso 4)**: La igualdad `new_password == current_password`
se evalúa sobre los strings **antes** de la derivación costosa de la llave candidata (paso 5).
Si son idénticos se lanza `ValueError` inmediatamente (FR-018), ahorrando una llamada Argon2id.

---

## Invariantes de seguridad

- `new_salt ≠ session.salt_b64` con probabilidad criptográficamente negligible de colisión
  (16 bytes aleatorios; constitución Principio III).
- `new_nonce` único respecto a `new_key` (AES-GCM: nonce de 12 bytes aleatorio; unicidad
  garantizada por generación aleatoria, probabilidad de colisión < 2⁻⁹⁶).
- Los metadatos en el archivo resultante son auténticos: modificarlos produce fallo de tag GCM.
- Si se lanza cualquier excepción, el archivo de bóveda permanece byte a byte idéntico al
  estado previo a la llamada.
