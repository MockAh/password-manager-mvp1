# Research: Cambiar Contraseña Maestra (Rotación)

**Feature**: `002-change-master-password`
**Date**: 2026-06-29
**Phase**: Plan Phase 0 — Resolución de incógnitas técnicas

---

## 1. Arquitectura de la rotación — "un blob, no entrada por entrada"

**Decision**: La bóveda es UN solo blob cifrado (AES-256-GCM sobre el JSON serializado de
`VaultPayload`). Rotar la contraseña maestra = re-cifrar ese único blob. El coste está dominado
por **dos llamadas Argon2id** (una para verificar la maestra actual, otra para derivar la llave
nueva), **no** por el número de entradas.

**Rationale**: La implementación existente en `src/vault/service.py` confirma este diseño.
`create_vault` y `unlock_vault` operan sobre el payload completo. La rotación sigue el mismo
patrón sin modificar ninguna primitiva.

**Alternatives considered**: Re-cifrar entrada por entrada (innecesario y más complejo; además
rompería la semántica del formato de archivo).

---

## 2. Verificación de la contraseña maestra actual en sesión abierta

**Decision**: Re-derivar la llave desde la contraseña introducida usando los parámetros KDF y el
salt almacenados en `_session` (`salt_b64`, `kdf_params`), y comparar byte a byte con
`_session.derived_key` usando `hmac.compare_digest` (comparación en tiempo constante).

**Rationale**: La sesión ya está abierta; la llave correcta está en memoria. Una sola llamada
Argon2id es suficiente para verificar. No se accede a disco; no hay ventana de corrupción.

**Alternatives considered**: Re-descifrar el archivo de disco — innecesario (la llave ya está en
memoria), más caro (requiere I/O), no aporta seguridad adicional.

---

## 3. Decisión sobre NFR-007 en el contexto de re-autenticación

**Context**: NFR-007 exige que en la pantalla de desbloqueo los errores de "contraseña
incorrecta" y "archivo dañado" sean indistinguibles (evitar oracle de existencia de bóveda
válida). En la rotación, la bóveda ya está desbloqueada y en memoria.

**Decision**: En el flujo de `change_master_password`, el rechazo por contraseña actual
incorrecta emite un mensaje **claro y específico** (`"Contraseña maestra actual incorrecta."`),
distinto del mensaje genérico de `unlock_vault`. La indistinguibilidad de NFR-007 se mantiene
**exclusivamente en la pantalla de desbloqueo**.

**Rationale**: La bóveda ya está abierta; el atacante ya sabe que existe y está desbloqueada.
No hay oracle de existencia. Un mensaje claro mejora la UX (el usuario sabe que tecleó mal la
actual, no que la bóveda está dañada) sin abrir ningún nuevo vector. La constitución exige
errores seguros pero no prohíbe mensajes específicos cuando no hay información sensible nueva
que filtrar.

**Alternatives considered**: Mensaje genérico igual que en unlock — sería correcto en seguridad
pero peor en usabilidad sin beneficio real (constitución, Principio VII).

---

## 4. Modelo de hilos y no-bloqueo de la UI (NFR-009)

**Context**: Tkinter no es thread-safe. La derivación Argon2id (~200-350 ms) y el cifrado
se ejecutan en el hilo principal si no se separan.

**Decision**: Ejecutar `change_master_password` en un `threading.Thread` de fondo. Las
actualizaciones de la UI se despachan al hilo principal vía `widget.after(0, callback)`.
El diálogo modal gestiona:
1. Pre-validaciones (comparación de identidad, longitud mínima) en el hilo principal.
2. Lanzamiento del thread de fondo con la contraseña actual y la nueva.
3. El thread de fondo llama a `VaultService.change_master_password()` (bloqueante).
4. Al terminar (éxito o error), el thread despacha el resultado con `after(0, ...)`.
5. El botón de confirmar se deshabilita durante la operación; un label/spinner muestra progreso.

**Rationale**: Patrón estándar para Tkinter con operaciones costosas. Ya existe en el proyecto
(e.g., derivación en `create_vault` y `unlock_vault` usadas desde `app.py`).

**Alternatives considered**: `concurrent.futures.ThreadPoolExecutor` — válido pero
innecesario para una sola operación; `threading.Thread` es suficiente y sin overhead.

---

## 5. Cancelación de la operación (NFR-009)

**Decision**: La cancelación solo es semánticamente válida **antes del commit**. Una vez que
`os.replace` completa el reemplazo atómico, la operación no es reversible. El flujo es:

```
[confirm] → [validate] → [thread: verify current key] → [thread: derive new key]
   → [thread: encrypt] → [thread: write temp file] → [thread: os.replace ← COMMIT]
   → [thread: zero keys + update session] → [after(0): show success]
```

El botón "Cancelar" se deshabilita en cuanto el thread arranca. Si el usuario cierra la ventana
durante la operación de fondo, el thread completa de forma segura (la atomicidad garantiza la
consistencia). La cancelación visible al usuario solo es posible antes de pulsar "Confirmar".

**Rationale**: Simplifica el modelo de concurrencia; no requiere `threading.Event` ni
señalización de cancelación al thread. La operación completa en ~300-600 ms (2 Argon2id +
serialización + cifrado + write); el usuario no necesita cancelarla una vez iniciada.

---

## 6. Suspensión del auto-bloqueo durante la rotación (FR-021)

**Decision**: Añadir dos métodos públicos a `VaultService`:
- `suspend_auto_lock() → None`: llama a `_cancel_inactivity_timer()` sin bloquear la sesión.
- `resume_auto_lock() → None`: llama a `_start_inactivity_timer()` para reiniciar desde cero.

El diálogo de cambio de maestra llama a `suspend_auto_lock()` al confirmar la operación y a
`resume_auto_lock()` en el callback `after(0, ...)` que recibe el resultado (éxito o error).

**Rationale**: Los métodos `_cancel_inactivity_timer` y `_start_inactivity_timer` ya existen;
solo se necesitan wrappers públicos. El diseño es mínimo y no introduce nuevo estado.

**Alternatives considered**: Flag `_timer_suspended: bool` en `VaultService` — innecesario
para este caso de uso; los wrappers directos son suficientes.

---

## 7. Higiene de memoria — límites reales en Python (NFR-004)

**Decision**: Los objetos `str` de Python son inmutables; no se pueden sobreescribir. Se acepta
esta limitación del runtime y se mitiga con:
- **Claves derivadas** (`bytearray`): se sobreescriben con ceros explícitamente con
  `VaultSession.zero_key()` (ya implementado) y en el método `change_master_password` para la
  clave antigua y la nueva tan pronto como no son necesarias.
- **Contraseñas** (`str`): se limita su tiempo de vida al scope del método y se liberan las
  referencias en cuanto dejan de ser necesarias. No se almacenan en ningún atributo de instancia.
- **Documentar la limitación** en el código como comentario explícito (auditable).

**Rationale**: Es la práctica estándar para Python en gestores de contraseñas. Ninguna librería
del ecosistema Python garantiza zeroing completo de strings (CPython no lo expone). La
constitución exige "minimizar el tiempo de vida" — no requiere zeroing imposible.

---

## 8. Estrategia de persistencia atómica (NFR-002)

**Decision**: Reutilizar exactamente `repository.save_vault_file()` que ya implementa
`tempfile.NamedTemporaryFile(dir=vault_dir, delete=False)` + `os.replace(temp_path, vault_path)`.
El método `change_master_password` en `VaultService` construye el nuevo `vault_data` dict y
llama a `repository.save_vault_file(path, vault_data)`. No se escribe nueva lógica de
persistencia atómica.

**Rationale**: La primitiva ya está implementada, probada y auditada. Usarla directamente
cumple el mandato de "no reinventar nada".

---

## 9. No se introducen primitivas criptográficas nuevas

**Audit**: La rotación usa exclusivamente:
- `crypto.kdf.generate_salt()` — ya existente.
- `crypto.kdf.derive_key(password, salt)` — ya existente.
- `crypto.vault_cipher.encrypt(plaintext, key, envelope_meta)` — ya existente.
- `crypto.vault_cipher.build_aad(version, kdf, kdf_params, salt_b64)` — ya existente (implícita
  en `encrypt`).
- `repository.save_vault_file(path, data)` — ya existente.
- `hmac.compare_digest(a, b)` — stdlib Python, no es una primitiva nueva.

**Conclusion**: Cero primitivas nuevas. Cumple el mandato de la constitución y del usuario.
