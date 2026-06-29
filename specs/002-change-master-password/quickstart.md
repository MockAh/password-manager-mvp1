# Quickstart: Validación de Cambio de Contraseña Maestra

**Feature**: `002-change-master-password`
**Date**: 2026-06-29

---

## Prerrequisitos

```bash
# Desde la raíz del repositorio
uv sync          # instala dependencias (argon2-cffi, cryptography, pytest, etc.)
uv run pytest --version   # verificar que pytest está disponible
```

---

## Escenario 1 — Rotación exitosa y verificación (SC-001)

```bash
# Ejecutar los tests de integración de rotación
uv run pytest tests/integration/test_vault_roundtrip.py -v -k "master_password"

# Ejecutar el test de rotación de la capa de servicio
uv run pytest tests/unit/test_vault_service.py -v -k "change_master"
```

**Resultado esperado**: todos los tests pasan. El test de integración:
1. Crea una bóveda con entradas.
2. Rota la contraseña maestra (old → new).
3. Verifica que `unlock_vault(path, new_password)` abre la bóveda con todas las entradas.
4. Verifica que `unlock_vault(path, old_password)` lanza `WrongPasswordError`.

---

## Escenario 2 — Atomicidad ante interrupción (SC-002, NFR-002)

```bash
uv run pytest tests/unit/test_vault_service.py -v -k "atomic"
```

**Resultado esperado**: el test simula una interrupción abrupta antes y después del commit
(`os.replace`) parcheando `repository.save_vault_file`. Verifica que:
- Antes del commit → archivo original intacto, descifrable con contraseña anterior.
- Después del commit → archivo nuevo completo, descifrable con contraseña nueva.
- En ambos casos → sin archivos temporales residuales.

---

## Escenario 3 — Anti-degradación via AAD (SC-004, NFR-003)

```bash
uv run pytest tests/unit/test_vault_service.py -v -k "aad or tamper"
# o alternativamente:
uv run pytest tests/integration/test_tamper_detection.py -v
```

**Resultado esperado**: el test modifica manualmente los metadatos del archivo re-cifrado
(p.ej. reduce `memory_cost`) e intenta abrirlo → `WrongPasswordError` (fallo de tag GCM).

---

## Escenario 4 — Maestra actual incorrecta; archivo intacto (SC-003)

```bash
uv run pytest tests/unit/test_vault_service.py -v -k "wrong_current"
```

**Resultado esperado**: llamar a `change_master_password(wrong_current, new)` lanza
`WrongPasswordError`; el archivo de bóveda queda byte a byte idéntico al estado previo.

---

## Escenario 5 — Validaciones de la nueva contraseña (US4)

```bash
uv run pytest tests/unit/test_vault_service.py -v -k "validation or identical or too_short"
```

**Resultado esperado**:
- Nueva contraseña idéntica a la actual → `ValueError`.
- Nueva contraseña < 12 caracteres → `ValueError`.
- Confirmación que no coincide (validado en la UI) → gestionado en el diálogo.

---

## Escenario 6 — Ausencia de restos en disco (SC-005, NFR-005)

```bash
uv run pytest tests/unit/test_vault_service.py -v -k "no_residue or cleanup"
```

**Resultado esperado**: tras rotación exitosa y tras rotación fallida, el directorio de la
bóveda contiene exactamente un archivo `.vault`; no hay archivos temporales.

---

## Suite completa del servicio de rotación (cobertura ≥ 95 %)

```bash
uv run pytest tests/unit/test_vault_service.py -v
uv run pytest tests/integration/ -v
```

---

## Cobertura de la feature

```bash
uv run pytest tests/ --cov=vault.service --cov=vault.repository --cov=crypto \
  --cov-report=term-missing -q
```

**Objetivo**: cobertura ≥ 95 % sobre `vault/service.py` (constitución Principio VI).

---

## Validación manual de la UI (opcional)

```bash
uv run python -m vault_manager
```

1. Crear o abrir una bóveda existente e introducir alguna entrada.
2. En la vista principal desbloqueada, activar "Cambiar contraseña maestra…".
3. Introducir la contraseña actual (correcta) y una nueva con confirmación.
4. Verificar mensaje de éxito.
5. Cerrar la aplicación; reabrir; introducir la nueva contraseña → bóveda abierta con entradas.
6. Intentar abrir con la contraseña anterior → error de autenticación.

---

## Referencias

- [spec.md](spec.md) — SC-001 a SC-007
- [data-model.md](data-model.md) — transiciones de estado
- [contracts/vault-service-interface.md](contracts/vault-service-interface.md) — secuencia interna
- [research.md](research.md) — decisiones de diseño (threading, memoria, atomicidad)
