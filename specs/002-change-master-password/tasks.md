---
description: "Tasks for 002-change-master-password"
---

# Tasks: Cambiar Contraseña Maestra (Rotación)

**Feature Branch**: `002-change-master-password`
**Date**: 2026-06-29
**Input**: [spec.md](spec.md) · [plan.md](plan.md) · [data-model.md](data-model.md) · [contracts/vault-service-interface.md](contracts/vault-service-interface.md) · [research.md](research.md)

---

## Phase 1: Setup

**Purpose**: Verificar que la suite de tests existente está en verde antes de añadir código.
No se crea ningún módulo nuevo en esta fase.

- [ ] T001 Ejecutar suite existente (`uv run pytest tests/ -q`) y confirmar que todos los tests pasan; registrar el recuento de tests como baseline en un comentario del commit

---

## Phase 2: Foundational — Suspensión del Auto-bloqueo

**Purpose**: Exponer `suspend_auto_lock` / `resume_auto_lock` en `VaultService` antes de
cualquier implementación de rotación o UI. Son prerrequisito de US3 (timer durante rotación)
y del diálogo modal (FR-021).

**⚠️ CRÍTICO**: Las fases US1–US4 y la UI no pueden completarse sin este fundamento.

- [ ] T002 [TDD] Escribir tests T-R16 y T-R17 en `tests/unit/test_vault_service.py`: T-R16 verifica que `suspend_auto_lock()` cancela el timer de inactividad sin bloquear la sesión; T-R17 verifica que `resume_auto_lock()` reinicia el timer desde cero — ambos tests deben FALLAR antes de T003 · FR-021
- [ ] T003 Implementar `suspend_auto_lock()` y `resume_auto_lock()` en `src/vault/service.py` como wrappers de los métodos privados `_cancel_inactivity_timer` y `_start_inactivity_timer` ya existentes; los tests T-R16 y T-R17 deben pasar tras este commit · FR-021

**Checkpoint**: `suspend_auto_lock`/`resume_auto_lock` disponibles y probadas — implementación de rotación puede comenzar

---

## Phase 3: User Story 1 — Rotación Exitosa de la Contraseña Maestra (Priority: P1) 🎯 MVP

**Goal**: `VaultService.change_master_password()` implementado y probado; una bóveda con entradas puede rotarse y seguir accesible solo con la nueva contraseña.

**Independent Test**: `uv run pytest tests/unit/test_vault_service.py -k "change_master" tests/integration/test_vault_roundtrip.py -k "rotation" -v`

### Tests para User Story 1 *(escribir ANTES de la implementación — deben FALLAR)*

- [ ] T004 [P] [US1] Escribir tests T-R01, T-R02, T-R03 y T-R20 en `tests/unit/test_vault_service.py`: T-R01 verifica que el salt en los metadatos es distinto al anterior tras la rotación; T-R02 verifica que `unlock_vault` con la nueva contraseña abre la bóveda con entradas intactas; T-R03 verifica que `unlock_vault` con la contraseña anterior lanza `WrongPasswordError`; T-R20 lee el campo `nonce` del archivo de bóveda antes y después de la rotación y verifica que difieren (nonce único por llave) · FR-006 · FR-008 · NFR-001 · SC-001
- [ ] T005 [P] [US1] Escribir test T-R04 en `tests/unit/test_vault_service.py`: verificar que tras `change_master_password` exitoso `service.is_unlocked` es `True` y `service._session.derived_key` contiene la llave nueva (distinta de la antigua) · FR-016
- [ ] T006 [P] [US1] Escribir tests T-R18 y T-R19 en `tests/integration/test_vault_roundtrip.py`: T-R18 roundtrip completo (crear bóveda → añadir entradas → rotar → cerrar → reabrir con nueva maestra → verificar entradas); T-R19 doble rotación consecutiva verificando que los dos salts generados son distintos entre sí y distintos al original · NFR-001 · SC-001

### Implementación de User Story 1

- [ ] T007 [US1] Implementar `change_master_password(self, current_password: str, new_password: str) -> None` en `src/vault/service.py`: **primero** añadir un esqueleto con `raise NotImplementedError` para que todos los tests (T-R01–T-R17, T-R20) sean importables y fallen por comportamiento, no por `ImportError`; **luego** completar la implementación completa siguiendo `contracts/vault-service-interface.md`: (1) `_require_unlocked()`; (2) validaciones baratas (vacío, longitud < 12, identidad); (3) re-derivar llave candidata con `derive_key(current_password, b64decode(session.salt_b64))` + comparar con `hmac.compare_digest` → `WrongPasswordError("Contraseña maestra actual incorrecta.")` si falla; (4) `zero(candidata)` en bloque `finally`; (5) `new_salt = generate_salt()`; (6) `new_key = derive_key(new_password, new_salt)` con los mismos `kdf_params` (FR-017); (7) construir `new_envelope_meta`; (8) `encrypt(plaintext, new_key, new_envelope_meta)` con nonce nuevo; (9) `repository.save_vault_file(path, vault_data)` (commit atómico); (10) `zero(session.derived_key)` sobre la referencia original del objeto en sesión; (11) `session.derived_key = new_key`; `session.salt_b64 = new_salt_b64`; en excepción post-paso-6: `zero(new_key)` en `finally` · FR-003 · FR-006 · FR-007 · FR-008 · FR-009 · FR-010 · FR-011 · FR-013 · FR-016 · FR-017 · NFR-001 · NFR-002 · NFR-003 · NFR-004

**Checkpoint**: US1 MVP completo — rotación exitosa funciona end-to-end; T-R01–T-R04, T-R18, T-R19 pasan

---

## Phase 4: User Story 2 — Re-autenticación Explícita con la Maestra Actual (Priority: P1)

**Goal**: Contraseña actual incorrecta → error específico y archivo intacto; bóveda bloqueada → error de sesión.

**Independent Test**: `uv run pytest tests/unit/test_vault_service.py -k "wrong_current or locked" -v`

### Tests para User Story 2 *(escribir en paralelo con los tests de US1, antes de la implementación completa de T007)*

- [ ] T008 [P] [US2] Escribir test T-R11 en `tests/unit/test_vault_service.py`: llamar a `change_master_password` con contraseña actual incorrecta verifica que (a) se lanza `WrongPasswordError`, (b) el mensaje de excepción es "Contraseña maestra actual incorrecta." (no el mensaje genérico de desbloqueo), (c) el archivo de bóveda permanece byte a byte idéntico al estado previo · FR-003 · FR-004 · NFR-007 · SC-003
- [ ] T009 [P] [US2] Escribir test T-R15 en `tests/unit/test_vault_service.py`: (a) llamar a `change_master_password` con la bóveda bloqueada verifica que se lanza `VaultLockedError` sin ningún acceso a disco; (b) llamar con `current_password=""` (bóveda desbloqueada) verifica que se lanza `WrongPasswordError` antes de cualquier operación de re-cifrado — la re-autenticación no puede omitirse con una cadena vacía · FR-001 · FR-002

**Checkpoint**: US2 completo — re-auth verificada; T-R11, T-R15 pasan tras T007

---

## Phase 5: User Story 3 — Resistencia a Interrupciones y Consistencia (Priority: P1)

**Goal**: Interrupción antes del commit → bóveda original intacta; después → bóveda nueva completa; sin residuos; auto-bloqueo suspendido durante la operación.

**Independent Test**: `uv run pytest tests/unit/test_vault_service.py -k "atomic or aad or tamper or autolock" -v`

### Tests para User Story 3

- [ ] T010 [P] [US3] Escribir test T-R07 en `tests/unit/test_vault_service.py`: parchear `os.replace` directamente (no `repository.save_vault_file`) para lanzar `OSError`, simulando el escenario “archivo temporal completamente escrito pero reemplazo fallido”; verificar que (a) el archivo temporal es eliminado por el mecanismo de limpieza de `save_vault_file`, (b) el archivo original permanece intacto y sigue siendo descifrable con la contraseña anterior, y (c) no quedan archivos temporales residuales en el directorio · NFR-002 · FR-011 · FR-012 · SC-002
- [ ] T011 [P] [US3] Escribir test T-R08 en `tests/unit/test_vault_service.py`: simular interrupción inmediatamente después del commit (mockear la actualización de sesión post-replace); verificar que el archivo en disco es el nuevo y es descifrable con la nueva contraseña · NFR-002 · SC-002
- [ ] T012 [P] [US3] Escribir tests T-R09 y T-R10 en `tests/unit/test_vault_service.py`: T-R09 modifica `kdf_params.memory_cost` en el archivo re-cifrado y verifica que `unlock_vault` lanza `WrongPasswordError` (fallo de tag GCM por AAD inválida); T-R10 modifica el campo `salt` en los metadatos y verifica el mismo fallo · NFR-003 · FR-009 · SC-004
- [ ] T013 [US3] Escribir test T-R17 en `tests/unit/test_vault_service.py`: configurar `VaultService` con timeout de auto-bloqueo de 1 segundo; llamar a `suspend_auto_lock()`, esperar 1.5 s, verificar que la bóveda sigue desbloqueada; llamar a `resume_auto_lock()` y verificar que el timer se reinicia desde cero · FR-021 · US3 Ac. Sc. 5 (depends on T003)

**Checkpoint**: US3 completo — atomicidad y AAD verificadas; T-R07–T-R10, T-R17 pasan

---

## Phase 6: User Story 5 — Higiene de Memoria y Ausencia de Restos en Disco (Priority: P1)

**Goal**: Llave antigua en ceros tras rotación exitosa (verificado sobre el objeto original); sin archivos temporales ni copias bajo la contraseña anterior en ningún escenario.

**Independent Test**: `uv run pytest tests/unit/test_vault_service.py -k "zero or residue or cleanup" -v`

### Tests para User Story 5

- [ ] T014 [P] [US5] Escribir test T-R05 en `tests/unit/test_vault_service.py`: guardar referencia al `bytearray` de `session.derived_key` **antes** de la rotación (`old_key_ref = service._session.derived_key`); llamar a `change_master_password`; verificar que `all(b == 0 for b in old_key_ref)` es `True` — es decir, el zeroing afecta al objeto original, no a una copia. `derive_key` ya devuelve `bytearray`, por lo que `zero()` (`for i in range(len(k)): k[i] = 0`) sobre `session.derived_key` es efectivo sin conversiones · NFR-004 · FR-013 · SC-005
- [ ] T015 [P] [US5] Escribir test T-R06 en `tests/unit/test_vault_service.py`: tras rotación exitosa y tras rotación fallida (contraseña incorrecta), listar archivos en el directorio de la bóveda y verificar que no existe ningún archivo temporal (patrón `*.tmp`, `*.part`, o cualquier archivo que no sea el `.vault` original); en el caso exitoso verificar además que `unlock_vault(path, old_password)` falla · NFR-005 · FR-012 · FR-014 · SC-005

**Checkpoint**: US5 completo — T-R05, T-R06 pasan

---

## Phase 7: User Story 4 — Validación de la Nueva Contraseña (Priority: P2)

**Goal**: Las cuatro validaciones baratas (vacío, longitud, confirmación, identidad) rechazan entradas inválidas antes de cualquier operación costosa.

**Independent Test**: `uv run pytest tests/unit/test_vault_service.py -k "validation or identical or too_short or empty" -v`

### Tests para User Story 4

- [ ] T016 [P] [US4] Escribir tests T-R12 y T-R13 en `tests/unit/test_vault_service.py`: T-R12 llama a `change_master_password(current, current)` y verifica que lanza `ValueError` con mensaje que indica identidad (sin derivación de llave — debe fallar antes del Argon2id); T-R13 llama con nueva contraseña de 11 caracteres y verifica `ValueError` con mención de 12 caracteres mínimos · FR-018 · FR-019 · US4 Ac. Sc. 4 y 5
- [ ] T017 [P] [US4] Escribir test T-R14 en `tests/unit/test_vault_service.py`: llamar a `change_master_password` con `new_password=""` y verificar `ValueError`; verificar que no se ha accedido a disco (archivo sin modificar) · FR-005 · US4 Ac. Sc. 2

### Revisión del orden de validaciones

- [ ] T018 [US4] Revisar la implementación de `change_master_password` en `src/vault/service.py` y verificar que el orden de validaciones baratas es (1) vacío → (2) longitud < 12 → (3) confirmación [nota: confirmación se valida en la UI, no en el servicio] → (4) identidad `new == current` → (5) re-autenticación Argon2id; documentar el orden con un comentario inline para facilitar auditoría · FR-018 · FR-019 · data-model.md §Reglas de validación

**Checkpoint**: US4 completo — T-R12–T-R14 pasan; validaciones baratas preceden a la derivación KDF

---

## Phase 8: UI — Diálogo Modal y Punto de Entrada

**Goal**: `ChangePasswordDialog` funcional como `Toplevel` modal; accesible desde `MainView`; no-bloqueante; teclear en los campos cuenta como actividad de inactividad.

### Implementación de UI (sin tests automáticos de Tkinter — validar con quickstart.md)

- [ ] T019 [P] [US1] Crear `src/ui/views/change_password_dialog.py` con la estructura del diálogo: tres `Entry(show="*")` (contraseña actual, nueva, confirmación), botones "Mostrar/Ocultar" para cada campo, indicador de fortaleza de la nueva contraseña (etiqueta de texto con color: rojo si < 12 chars, ámbar 12–15, verde ≥ 16; reutilizar criterio de 001 si existe), label de estado/progreso, botones "Confirmar" y "Cancelar" · FR-001 · FR-019 · FR-020 · US4 Ac. Sc. 6
- [ ] T020 [US1] Implementar la lógica no-bloqueante de rotación en `ChangePasswordDialog` en `src/ui/views/change_password_dialog.py`: (a) pre-flight en hilo principal (vacío, longitud, confirmación, identidad — FR-018, FR-019); (b) `service.suspend_auto_lock()`; (c) deshabilitar botones + mostrar "Cambiando contraseña…"; (d) `threading.Thread(target=_run_rotation, daemon=True).start()`; (e) `_run_rotation` llama a `service.change_master_password(current_pw, new_pw)` y despacha resultado con `root.after(0, _on_success)` o `root.after(0, _on_error, msg)`; (f) `_on_success`/`_on_error` en hilo principal llaman a `service.resume_auto_lock()`, reenvian el control a la UI y cierran el diálogo o muestran el error · NFR-008 · NFR-009 · FR-015 · FR-016 · FR-021 (depends on T019, T003)
- [ ] T021 [US4] Enlazar `<KeyRelease>` en los tres campos `Entry` del diálogo a `self._app.vault_service.record_activity()` en `src/ui/views/change_password_dialog.py` para que teclear en los campos cuente como actividad de usuario que reinicia el temporizador de inactividad; documentar en el código que si el diálogo es abandonado antes de pulsar "Confirmar", el timer de auto-bloqueo corre con normalidad · FR-021 · constitución Principio VII (depends on T020)
- [ ] T022 [US1] Añadir ítem de menú o botón "Cambiar contraseña maestra…" en la barra de acciones de `MainView` en `src/ui/views/main_view.py`; el botón/ítem solo es visible en `MainView` (bóveda desbloqueada); al activarlo instanciar `ChangePasswordDialog(parent=self, app=self._app)` y llamar a `grab_set()` para hacerlo modal; no añadir ningún punto de entrada en `UnlockView` ni en `CreateVaultView` · FR-001 · US1 Ac. Sc. 1 (depends on T020)

**Checkpoint**: Feature completa — flujo end-to-end validable con `quickstart.md` escenario de validación manual

---

## Phase 9: Polish — Documentación de Limitaciones Conscientes

**Goal**: Registrar en el código las limitaciones conocidas e inevitables para facilitar auditorías futuras y evitar que un revisor las interprete como bugs.

- [ ] T023 Añadir bloque de comentario `# Memory hygiene — known limitations` en `src/vault/service.py` (junto a `change_master_password`) y en `src/ui/views/change_password_dialog.py` documentando: (a) los objetos `str` de contraseña en CPython son inmutables — no es posible sobreescribirlos; se mitiga liberando referencias en cuanto salen de scope y evitando almacenarlas en atributos de instancia; (b) los buffers internos de la biblioteca Argon2 (C) quedan fuera de nuestro control y no son accesibles desde Python; (c) el diálogo de cambio de contraseña suspende el auto-bloqueo durante la operación activa; si el usuario abandona el diálogo sin pulsar "Confirmar", el timer de inactividad corre con normalidad y teclear en los campos lo reinicia via `record_activity()`; (d) el zeroing de `bytearray` de clave es efectivo porque `derive_key` ya devuelve `bytearray` mutable — nunca copiar la llave a `bytes` antes de zeroizar · NFR-004 · research.md §7 · constitución Principio V (auditabilidad)

---

## Dependencies

```
T001
  └── T002 → T003
              ├── [Escribir todos los tests de servicio — paralelas entre sí, deben FALLAR]
              │   T004, T005, T006 (US1) · T008, T009 (US2)
              │   T010, T011, T012 (US3) · T014, T015 (US5) · T016, T017 (US4)
              │   T013 (US3 autolock — depends T003 directamente, no T007)
              └── T007 (esqueleto mínimo primero; implementación completa tras todos los tests en rojo)
                  ├── T018
                  └── T019
                      └── T020 (depends T003)
                              ├── T021
                              └── T022
T023 (puede hacerse al final, no bloquea nada)
```

## Parallel Execution Examples

**Tras T003** (foundational completa), las siguientes pueden avanzar en paralelo
(todas antes de la implementación completa de T007):
- T004 + T005 + T006 (escribir tests de US1)
- T008 + T009 (tests US2)
- T010 + T011 + T012 (tests US3)
- T013 (test autolock US3 — depends T003, puede ir junto a los anteriores)
- T014 + T015 (tests US5)
- T016 + T017 (tests US4)
- T019 (esqueleto del diálogo, independiente de los tests de servicio)

## Implementation Strategy

**MVP**: Completar hasta Phase 6 (US1–US5 del servicio) sin UI. Permite validar toda la lógica de seguridad con tests automáticos antes de tocar la capa visual.

**Incremento 2**: Phase 7 (US4 validaciones) + Phase 8 (UI). Entrega la feature completa.

**Incremento 3**: Phase 9 (documentación). No afecta a comportamiento.

## Trazabilidad FR / NFR → Tests

| Requisito | Test(s) | Tarea |
|-----------|---------|-------|
| FR-001 (entry point solo en main view) | T-R15 (VaultLockedError) | T009, T022 |
| FR-003 + FR-004 (verificar maestra actual) | T-R11 | T008 |
| FR-005 (confirmación coincidente) | pre-flight en diálogo | T020 |
| FR-006 + NFR-001 (salt nuevo) | T-R01, T-R19 | T004, T006 |
| FR-008 (nonce nuevo) | T-R20 (nonce distinto antes/después de rotar) | T004 |
| FR-009 + NFR-003 (AAD) | T-R09, T-R10 | T012 |
| FR-010 + FR-011 + NFR-002 (atómico) | T-R07, T-R08 | T010, T011 |
| FR-012 + NFR-005 (sin residuos) | T-R06 | T015 |
| FR-013 + NFR-004 (higiene memoria) | T-R05 | T014 |
| FR-014 + NFR-005 (sin copia antigua) | T-R06, T-R03 | T004, T015 |
| FR-015 + NFR-008 (feedback progreso) | validación manual | T020 |
| FR-016 (sesión desbloqueada con llave nueva) | T-R04 | T005 |
| FR-017 (kdf_params preservados) | T-R18 (roundtrip verifica desbloqueo) | T006 |
| FR-018 (rechazar idéntica) | T-R12 | T016 |
| FR-019 (longitud mínima 12) | T-R13 | T016 |
| FR-020 (indicador de fortaleza) | validación manual | T019 |
| FR-021 (suspender auto-bloqueo) | T-R16, T-R17 | T002, T003, T013 |
| NFR-007 (error específico re-auth) | T-R11 (mensaje exacto) | T008 |
| NFR-009 (no bloqueo UI) | validación manual (quickstart.md) | T020 |
| SC-001 | T-R02, T-R03, T-R18 | T004, T006 |
| SC-002 | T-R07, T-R08 | T010, T011 |
| SC-003 | T-R11 | T008 |
| SC-004 | T-R09, T-R10 | T012 |
| SC-005 | T-R06 | T015 |

## Constitution Compliance Check ✅

| Principio | Cobertura en las tareas |
|-----------|------------------------|
| I — Seguridad primero | Núcleo de seguridad (T002–T015) planificado antes que UI (T019–T022) |
| II — Offline | Sin tareas de red; sin dependencias nuevas con conectividad |
| III — AEAD + KDF | T007 reutiliza `derive_key`, `generate_salt`, `encrypt` sin modificarlas |
| IV — Sin recuperación | No se crea ningún mecanismo de bypass de la maestra actual |
| V — Auditabilidad | T023 documenta limitaciones; T018 documenta orden de validaciones |
| VI — Tests ≥ 95 % | 17 test tasks cubren todos los caminos de éxito, error y fallo |
| VII — UX consistente | T021 garantiza que el timer de inactividad se comporta coherentemente |
| VIII — Rendimiento | T020 ejecuta Argon2id en hilo de fondo; indicador si > 2 s |

**Primitivas criptográficas nuevas introducidas**: **ninguna**.
**Módulos nuevos no justificados**: **ninguno** — solo `change_password_dialog.py` como UI delgada.
