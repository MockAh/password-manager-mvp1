# Quickstart: Guía de Validación

**Feature**: `001-local-password-manager`
**Date**: 2026-06-17

Esta guía describe los escenarios de validación ejecutables que prueban que la feature funciona
de extremo a extremo. No incluye código de implementación; para eso, ver `tasks.md` (generado
por `/speckit.tasks`).

---

## Prerrequisitos

```bash
# Python 3.11+
python --version   # debe mostrar 3.11.x o superior

# Instalar dependencias de runtime y dev
pip install argon2-cffi cryptography pytest pytest-cov

# Verificar que no hay tráfico de red (opcional, para validar FR-019)
# Ejecutar la app bajo monitorización de red: ss -tp o lsof -i
```

---

## Escenario 1 — US1: Crear una Bóveda Nueva y Desbloquearla

**Prueba manual (GUI)**:
1. Ejecutar `python src/main.py`.
2. Seleccionar "Crear nueva bóveda".
3. Elegir una ubicación y nombre de archivo (e.g., `~/mi-boveda.vault`).
4. La aplicación DEBE mostrar el aviso de que la contraseña maestra no puede recuperarse.
5. Confirmar el aviso e introducir una contraseña maestra.
6. La interfaz principal debe mostrarse (bóveda vacía desbloqueada).
7. Cerrar la aplicación.
8. Verificar que `~/mi-boveda.vault` existe y que su contenido es JSON con campos `version`, `kdf`, `salt`, `nonce`, `ciphertext` — sin contraseñas en texto plano.
9. Volver a ejecutar `python src/main.py` → "Abrir bóveda existente" → seleccionar el archivo.
10. Introducir la contraseña correcta → la bóveda se desbloquea.
11. Introducir una contraseña incorrecta → acceso denegado, mensaje de error, sin datos expuestos.

**Prueba automatizada** (`tests/unit/test_vault_cipher.py`, `tests/integration/test_vault_roundtrip.py`):
```bash
pytest tests/unit/test_vault_cipher.py tests/integration/test_vault_roundtrip.py -v
```
Resultado esperado: todos los tests pasan.

---

## Escenario 2 — US2: Gestionar Entradas (CRUD)

**Prueba manual (GUI)**:
1. Con la bóveda desbloqueada, crear una nueva entrada:
   - Título: "GitHub", URL: "https://github.com", Usuario: "mi-usuario", Contraseña: "abc123!", Notas: "Cuenta personal".
2. La entrada debe aparecer en la lista.
3. Editar la entrada: cambiar la contraseña a "nuevaClave456!".
4. Bloquear y desbloquear la bóveda → la entrada editada persiste.
5. Eliminar la entrada: confirmar el diálogo → la entrada desaparece.
6. Cancelar la eliminación de otra entrada → la entrada permanece.

**Prueba automatizada** (`tests/unit/test_vault_service.py`):
```bash
pytest tests/unit/test_vault_service.py -v
```

---

## Escenario 3 — US3: Búsqueda en Tiempo Real

**Prueba manual (GUI)**:
1. Con 5+ entradas en la bóveda, escribir "git" en el campo de búsqueda.
2. La lista debe filtrar instantáneamente mostrando solo las entradas con "git" en el título o usuario.
3. Borrar el texto → se muestran todas las entradas.
4. Buscar un término sin coincidencias → mensaje de "sin resultados".

**Prueba de rendimiento** (verificar SC-003):
```bash
pytest tests/unit/test_vault_service.py::test_search_500_entries_under_100ms -v
```

---

## Escenario 4 — US4: Generar Contraseñas Seguras

**Prueba manual (GUI)**:
1. En el formulario de nueva entrada, abrir el generador de contraseñas.
2. Configurar longitud 24, solo minúsculas + dígitos.
3. Generar → el resultado tiene 24 caracteres y contiene solo letras minúsculas y dígitos.
4. Regenerar → el nuevo valor es diferente.
5. "Usar esta contraseña" → el campo contraseña de la entrada se rellena.

**Prueba automatizada** (`tests/unit/test_password_generator.py`):
```bash
pytest tests/unit/test_password_generator.py -v
```

---

## Escenario 5 — US5: Portapapeles con Borrado Automático

**Prueba manual (GUI)**:
1. Seleccionar una entrada y pulsar "Copiar contraseña".
2. Pegar en un editor de texto → el valor correcto aparece.
3. Esperar 20 segundos → intentar pegar → el portapapeles está vacío.
4. Copiar de nuevo. Antes de que pasen 20 s, bloquear la bóveda → el portapapeles se limpia inmediatamente.

**Nota**: Para prueba rápida, cambiar temporalmente el timeout a 5 s en `src/ui/clipboard.py`.

---

## Escenario 6 — US6: Organizar Entradas en Carpetas

**Prueba manual (GUI)**:
1. Crear dos carpetas: "Trabajo" y "Personal".
2. Mover dos entradas a "Trabajo" y una a "Personal".
3. Seleccionar "Trabajo" → solo se muestran las entradas de esa carpeta.
4. Seleccionar "Personal" → solo se muestra la entrada correspondiente.
5. Intentar eliminar "Trabajo" → aparece diálogo de confirmación informando que las 2 entradas pasarán a "Sin carpeta". Confirmar.
6. Las 2 entradas permanecen en "Sin carpeta".

---

## Escenario 7 — US7: Auto-bloqueo por Inactividad

**Prueba manual (GUI)**:
1. En la configuración de la aplicación, establecer el timeout de inactividad a 10 segundos.
2. Desbloquear la bóveda y no interactuar.
3. Tras ~10 s, la pantalla de desbloqueo debe mostrarse automáticamente.
4. Introducir la contraseña correcta → la bóveda se desbloquea y se retorna al estado anterior.

**Prueba automatizada** (`tests/unit/test_vault_service.py::test_inactivity_lock`):
```bash
pytest tests/unit/test_vault_service.py::test_inactivity_lock -v
```

---

## Escenario 8 — Seguridad: Tamper Detection y Archivo Corrupto

```bash
# Ejecutar la suite de seguridad completa
pytest tests/unit/test_vault_cipher.py tests/integration/test_tamper_detection.py -v
```

Casos cubiertos por los tests:
- Contraseña incorrecta → `WrongPasswordError`.
- Flip de un byte en `ciphertext` → `VaultCorruptError`.
- `nonce` modificado → `VaultCorruptError`.
- `ciphertext` truncado → `VaultCorruptError`.
- `salt` modificado → `WrongPasswordError` (clave derivada diferente → fallo GCM).
- JSON malformado → `VaultCorruptError`.
- Campo obligatorio ausente → `VaultCorruptError`.

---

## Validación de Cobertura de Tests

```bash
# Ejecutar todos los tests con reporte de cobertura
pytest --cov=src/crypto --cov-report=term-missing tests/

# Resultado esperado: cobertura src/crypto/ >= 95 %
```

---

## Validación de Cero Tráfico de Red (FR-019, SC-009)

```bash
# Linux: monitorizar conexiones de red mientras la app está en uso
ss -tp | grep python  # no debe mostrar ninguna conexión activa

# Alternativa con strace (operaciones de red):
strace -e trace=network python src/main.py 2>&1 | grep -v "ENOENT"
# No debe aparecer ninguna llamada a connect(), sendto(), etc.
```

---

## Validación de Rendimiento de KDF (Constitución III)

```bash
# Verificar que Argon2id tarda >= 100 ms en el hardware local
pytest tests/unit/test_kdf.py::test_kdf_minimum_duration -v -s
# El test mide el tiempo real de derivación y falla si es < 100 ms
```
