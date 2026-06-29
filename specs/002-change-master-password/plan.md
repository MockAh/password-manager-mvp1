# Implementation Plan: Cambiar Contraseña Maestra (Rotación)

**Branch**: `002-change-master-password` | **Date**: 2026-06-29 | **Spec**: [spec.md](spec.md)

---

## Summary

Añadir al proyecto existente `001-local-password-manager` la funcionalidad de rotar la
contraseña maestra de una bóveda ya desbloqueada. La rotación reutiliza íntegramente el núcleo
criptográfico de 001 (Argon2id KDF, AES-256-GCM con AAD, escritura atómica) sin introducir
ninguna primitiva nueva. El cambio se divide en tres piezas: un nuevo método
`VaultService.change_master_password()` en la capa de servicio, dos métodos auxiliares de
auto-bloqueo (`suspend_auto_lock` / `resume_auto_lock`), y un diálogo modal delgado
(`ChangePasswordDialog`) en la capa UI.

---

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: argon2-cffi (KDF), cryptography/PyCA (AES-256-GCM) — ambas ya
presentes en `pyproject.toml`. `hmac` (comparación en tiempo constante) de la stdlib.

**Storage**: Archivo `.vault` local — JSON cifrado con escritura atómica vía
`tempfile` + `os.replace` (ya implementado en `repository.save_vault_file`).

**Testing**: pytest + pytest-cov (ya configurado). TDD: tests primero.

**Target Platform**: Linux/macOS/Windows (escritorio, offline).

**Project Type**: Desktop app (Tkinter), extensión de proyecto existente.

**Performance Goals**: Derivación Argon2id ≥ 100 ms (mínimo constitucional) y ≤ 1 s en hardware
de referencia. Re-cifrado de bóveda completa (hasta 1.000 entradas) < 10 s total (NFR-008).

**Constraints**: 100 % offline (Principio II). Sin primitivas criptográficas nuevas. Sin
bloqueo de UI (NFR-009) — operación en hilo de fondo. Tkinter no es thread-safe: updates de UI
solo vía `widget.after(0, callback)`.

**Scale/Scope**: Bóveda única (ciclo 001). Bóvedas de hasta ~1.000 entradas como caso de
rendimiento objetivo.

---

## Constitution Check

*Evaluado contra `.specify/memory/constitution.md` — re-evaluado post-diseño al final del plan.*

| Principio | ¿Cumple? | Evidencia |
|-----------|----------|-----------|
| I — Seguridad por Diseño | ✅ | Re-auth explícita + salt nuevo + atómico + zeroing |
| II — Privacidad / Offline | ✅ | Cero operaciones de red; solo I/O local |
| III — Cifrado Autenticado + KDF | ✅ | AES-256-GCM existente + Argon2id + AAD re-vinculada |
| IV — Sin Recuperación | ✅ | Exige conocer la maestra actual; no hay backdoor |
| V — Calidad de Código | ✅ | Responsabilidad única por capa; sin primitivas directas |
| VI — Tests Automatizados | ✅ | Cobertura ≥ 95 % exigida; TDD; casos de seguridad cubiertos |
| VII — Consistencia UX | ✅ | Diálogo modal accesible solo con bóveda desbloqueada |
| VIII — Rendimiento | ✅ | Operación en hilo de fondo; indicador de progreso si > 2 s |

**Resultado: GATE PASSED.** No hay violaciones.

---

## Project Structure

### Documentation (this feature)

```text
specs/002-change-master-password/
├── plan.md                        # Este archivo
├── research.md                    # Decisiones técnicas (Phase 0)
├── data-model.md                  # Entidades afectadas y transiciones
├── quickstart.md                  # Guía de validación
├── contracts/
│   └── vault-service-interface.md # Contrato de change_master_password
├── checklists/
│   └── requirements.md            # Checklist de calidad de spec
└── tasks.md                       # Fase 2 — generado por /speckit.tasks
```

### Source Code — archivos afectados

```text
src/
├── vault/
│   └── service.py          # MODIFICAR: añadir change_master_password,
│                           #   suspend_auto_lock, resume_auto_lock
└── ui/
    ├── views/
    │   └── main_view.py    # MODIFICAR: añadir ítem de menú/botón "Cambiar contraseña…"
    └── views/
        └── change_password_dialog.py  # CREAR: diálogo modal nuevo

tests/
├── unit/
│   └── test_vault_service.py      # MODIFICAR: añadir casos de rotación
└── integration/
    └── test_vault_roundtrip.py    # MODIFICAR: añadir test de rotación e2e
```

**Structure Decision**: Single project (la feature es una extensión directa del proyecto 001).
No se crean nuevos módulos ni capas. Tres cambios en archivos existentes + un archivo nuevo de UI.

---

## Phase 0 — Research (completada)

Todas las incógnitas técnicas resueltas. Ver [research.md](research.md).

| Incógnita | Decisión |
|-----------|----------|
| NFR-007 en re-auth de sesión | Mensaje específico "contraseña actual incorrecta" — no genérico |
| Threading + Tkinter | Thread de fondo + `after(0, cb)` para UI updates |
| Cancelación | Solo antes de pulsar "Confirmar"; botón deshabilitado durante operación |
| Suspensión auto-bloqueo | `suspend_auto_lock()` / `resume_auto_lock()` en VaultService |
| Higiene de memoria en Python | Zeroing de `bytearray` (claves); strings liberados por scope |
| Persistencia atómica | Reutilizar `repository.save_vault_file()` sin cambios |
| Primitivas criptográficas | Cero nuevas — solo las ya existentes en `crypto/` |

---

## Phase 1 — Design

### 1.1 Capa de Servicio: `VaultService.change_master_password`

**Archivo**: `src/vault/service.py`

**Nuevo método** (ver contrato completo en [contracts/vault-service-interface.md](contracts/vault-service-interface.md)):

```python
def change_master_password(self, current_password: str, new_password: str) -> None
```

Secuencia interna:
1. `_require_unlocked()` → `VaultLockedError` si bloqueada.
2. Validaciones baratas (vacío, longitud < 12, identidad `new == current`).
3. Re-derivar llave candidata con `current_password` + `session.salt_b64` + `session.kdf_params`.
4. `hmac.compare_digest(candidate, session.derived_key)` → `WrongPasswordError` si falla.
5. `zero(candidate)`.
6. `new_salt = generate_salt()` — 16 bytes CSPRNG.
7. `new_key = derive_key(new_password, new_salt)` — mismos `kdf_params` (FR-017).
8. Construir `new_envelope_meta` con el nuevo salt.
9. `plaintext = json.dumps(session.payload.to_dict(), ...).encode("utf-8")`.
10. `new_nonce, ciphertext = encrypt(plaintext, new_key, new_envelope_meta)`.
11. Construir `vault_data` dict completo.
12. `repository.save_vault_file(session.vault_file_path, vault_data)` ← COMMIT atómico.
13. `zero(session.derived_key)` — limpiar llave antigua antes de reemplazarla.
14. `session.derived_key = new_key`; `session.salt_b64 = new_salt_b64` — actualizar sesión.
15. En cualquier excepción después del paso 6: `zero(new_key)` en bloque `finally`.

**Invariantes**:
- Si se lanza excepción en pasos 1–11: archivo intacto, sesión sin cambios.
- Si se lanza excepción en paso 12 (OSError): archivo temp eliminado por `save_vault_file`;
  archivo original intacto; `new_key` zerorizado en `finally`.
- Después del paso 12: la operación es irreversible (commit completo).

### 1.2 Capa de Servicio: métodos de auto-bloqueo

```python
def suspend_auto_lock(self) -> None:
    """Cancela el timer de inactividad sin bloquear la sesión (FR-021)."""
    self._cancel_inactivity_timer()

def resume_auto_lock(self) -> None:
    """Reinicia el timer de inactividad desde cero (FR-021)."""
    self._start_inactivity_timer()
```

Minimalistas: no añaden nuevo estado. Usan los métodos privados ya existentes.

### 1.3 UI: diálogo modal `ChangePasswordDialog`

**Archivo nuevo**: `src/ui/views/change_password_dialog.py`

**Responsabilidades** (todo lo visual; cero lógica de negocio):
- Tres campos `Entry` con `show="*"`: contraseña actual, nueva contraseña, confirmación.
- Botón "Mostrar/Ocultar" para cada campo (FR-005 UX).
- Indicador de fortaleza de la nueva contraseña (reutilizar el criterio de 001 si existe,
  o etiqueta de texto simple con color: rojo < 12 chars, ámbar 12–15, verde ≥ 16).
- Botón "Confirmar" — lanza la operación de fondo.
- Botón "Cancelar" — solo activo antes de pulsar "Confirmar".
- Label de estado/progreso ("Cambiando contraseña…" durante la operación).
- Validaciones de pre-vuelo en hilo principal (vacío, longitud, confirmación, identidad)
  **antes** de lanzar el thread.

**Flujo del diálogo**:
```
[usuario pulsa Confirmar]
  → validar (vacío / longitud / confirmación / identidad) en hilo principal
  → si falla: mostrar error inline, no lanzar thread
  → si ok:
    - service.suspend_auto_lock()
    - deshabilitar ambos botones
    - mostrar "Cambiando contraseña…"
    - threading.Thread(target=_run_rotation, daemon=True).start()

_run_rotation():
  try:
    service.change_master_password(current_pw, new_pw)
    root.after(0, _on_success)
  except WrongPasswordError as e:
    root.after(0, _on_error, str(e))
  except Exception as e:
    root.after(0, _on_error, "Error inesperado.")
  finally:
    root.after(0, lambda: service.resume_auto_lock())

_on_success():   # hilo principal
  service.resume_auto_lock()  # redundante pero seguro
  mostrar "Contraseña cambiada correctamente."
  cerrar diálogo tras breve pausa

_on_error(msg):  # hilo principal
  habilitar botones
  mostrar mensaje de error claro
  limpiar campos de contraseña
```

### 1.4 UI: punto de entrada en `MainView`

**Archivo**: `src/ui/views/main_view.py`

Añadir un ítem de menú o botón "Cambiar contraseña maestra…" en la barra de acciones de
`MainView`. Al activarlo, instanciar y mostrar `ChangePasswordDialog` como `Toplevel` modal
(`grab_set()`). El botón solo existe en `MainView` (bóveda desbloqueada); no aparece en
`UnlockView` ni en `CreateVaultView` (FR-001).

---

## Phase 1 — Constitution Check Post-Diseño

Re-evaluación tras los artefactos de diseño:

| Sutileza (IDEA §6) | Elemento del diseño que la cubre |
|--------------------|----------------------------------|
| Salt nuevo en cada rotación (NFR-001) | Paso 6: `generate_salt()` siempre; prohibición explícita de reutizar |
| Re-cifrado atómico (NFR-002) | Paso 12: `repository.save_vault_file` (temp + `os.replace`); invariante de excepción |
| Anti-degradación AAD (NFR-003) | Paso 8-10: `new_envelope_meta` con nuevo salt; `encrypt` incluye AAD automáticamente |
| Higiene de memoria (NFR-004) | Pasos 5, 13, finally: zeroing de bytearray; scope mínimo para strings |

**Componentes innecesarios detectados**: Ninguno. El diseño es el mínimo necesario para
implementar la feature sin over-engineering.

**Verificación de no-introducción de primitivas nuevas**: Confirmado. Ver [research.md §9](research.md).

---

## Complexity Tracking

*No hay violaciones de la Constitución que justificar.*

---

## Test Strategy (pytest, cobertura ≥ 95 %)

### Tests unitarios — `tests/unit/test_vault_service.py` (nuevos casos)

| ID | Descripción | Requisito |
|----|-------------|-----------|
| T-R01 | Rotación exitosa: salt nuevo ≠ salt anterior | NFR-001 |
| T-R02 | Rotación exitosa: nueva contraseña desbloquea | SC-001 |
| T-R03 | Rotación exitosa: contraseña anterior falla | SC-001 |
| T-R04 | Rotación exitosa: sesión sigue desbloqueada con llave nueva | FR-016 |
| T-R05 | Rotación exitosa: llave antigua zerorizada | NFR-004 |
| T-R06 | Rotación exitosa: sin archivos temporales residuales | NFR-005 |
| T-R07 | Atomicidad — interrupción antes del commit: archivo original intacto | NFR-002 |
| T-R08 | Atomicidad — interrupción después del commit: archivo nuevo correcto | NFR-002 |
| T-R09 | AAD: modificar `memory_cost` en disco → WrongPasswordError | NFR-003 |
| T-R10 | AAD: modificar `salt` en disco → WrongPasswordError | NFR-003 |
| T-R11 | Maestra actual incorrecta → WrongPasswordError; archivo intacto | SC-003 |
| T-R12 | Nueva contraseña idéntica a actual → ValueError | FR-018 |
| T-R13 | Nueva contraseña < 12 chars → ValueError | FR-019 |
| T-R14 | Nueva contraseña vacía → ValueError | FR-005 |
| T-R15 | Bóveda bloqueada → VaultLockedError | FR-001 |
| T-R16 | `suspend_auto_lock` cancela timer; `resume_auto_lock` lo reinicia | FR-021 |
| T-R17 | Timer suspendido durante rotación: no dispara auto-bloqueo | FR-021 |

### Tests de integración — `tests/integration/test_vault_roundtrip.py` (nuevos casos)

| ID | Descripción | Requisito |
|----|-------------|-----------|
| T-R18 | Roundtrip completo: crear → añadir entradas → rotar → reabrir con nueva maestra | SC-001 |
| T-R19 | Rotación doble: rotar dos veces consecutivas con salts distintos | NFR-001 |

