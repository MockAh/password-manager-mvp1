---
description: "Lista de tareas de implementación — Gestor de Contraseñas Local y Offline"
---

# Tasks: Gestor de Contraseñas Local y Offline

**Input**: `specs/001-local-password-manager/` — plan.md, spec.md, research.md, data-model.md, contracts/

**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅

**Tests**: Incluidos — explícitamente solicitados en los argumentos del plan y obligatorios para
todo código de seguridad según la Constitución (Principio VI). TDD aplicado en la capa crypto
(Fase 2); tests después de implementación en capas de negocio y UI.

**Organización**: Tareas agrupadas por historia de usuario para permitir implementación y prueba
independientes de cada historia.

## Formato: `[ID] [P?] [Story?] Descripción`

- **[P]**: Puede ejecutarse en paralelo (archivos distintos, sin dependencias incompletas)
- **[Story]**: Historia de usuario a la que pertenece la tarea (US1–US7)
- Todas las rutas son relativas a la raíz del repositorio

## Convenciones de Ruta

- Proyecto único: `src/`, `tests/` en la raíz del repositorio
- Módulo criptográfico aislado: `src/crypto/` — única capa con acceso a primitivas
- Capa de datos: `src/vault/` — sin dependencias de Tkinter
- Generador: `src/generator/` — sin dependencias de Tkinter
- Interfaz: `src/ui/` — sin lógica de negocio ni acceso directo a `src/crypto/`

---

## Phase 1: Setup (Infraestructura compartida)

**Propósito**: Inicialización del proyecto y estructura base

- [X] T001 Crear `pyproject.toml` en la raíz con metadatos del proyecto, dependencias runtime (`argon2-cffi>=23.1`, `cryptography>=42.0`), dependencias dev (`pytest>=8.0`, `pytest-cov>=5.0`) y configuración de pytest (`testpaths=["tests"]`) y coverage (`source=["src/crypto"]`)
- [X] T002 [P] Crear estructura de paquetes `src/` con todos los `__init__.py` según plan.md: `src/`, `src/crypto/`, `src/vault/`, `src/generator/`, `src/ui/`, `src/ui/views/`
- [X] T003 [P] Crear estructura de tests `tests/` con `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py` y `tests/conftest.py` (fixtures compartidas: `tmp_vault_path`, `vault_password`)

---

## Phase 2: Foundational (Prerrequisitos bloqueantes)

**Propósito**: Capa criptográfica y modelo de datos — DEBE completarse antes de cualquier
historia de usuario. TDD obligatorio para código de seguridad (Constitución, Principio VI).

**⚠️ CRÍTICO**: Ninguna historia de usuario puede comenzar hasta que esta fase esté completa y
todos los tests de seguridad pasen.

- [X] T004 Escribir tests de seguridad para la KDF en `tests/unit/test_kdf.py`: derivación determinista (mismo password + salt → misma clave), unicidad de salt (`os.urandom` produce valores distintos), longitud de clave resultante = 32 bytes, tiempo de derivación ≥ 100 ms en hardware local (assert), parámetros por defecto correctos (`time_cost=3`, `memory_cost=65536`, `parallelism=1`, `hash_len=32`)
- [X] T005 Implementar `src/crypto/kdf.py` — constantes `ARGON2_*`, función `derive_key(password: str, salt: bytes) -> bytearray` usando `argon2.low_level.hash_secret_raw`; función `generate_salt() -> bytes` con `os.urandom(16)`; todos los tests T004 deben pasar
- [X] T006 Escribir tests de seguridad AEAD en `tests/unit/test_vault_cipher.py`: roundtrip cifrado/descifrado correcto, contraseña incorrecta → `InvalidTag`, flip de un byte en `ciphertext` → `InvalidTag`, modificar `kdf_params.memory_cost` en AAD → `InvalidTag`, modificar `version` en AAD → `InvalidTag`, `nonce` truncado → `InvalidTag`, ciphertext vacío → `InvalidTag`
- [X] T007 Implementar `src/crypto/vault_cipher.py` — `build_aad(version, kdf, kdf_params, salt_b64) -> bytes` (JSON canónico `sort_keys=True` UTF-8); `encrypt(plaintext, key, envelope_meta) -> tuple[bytes, bytes]` usando `AESGCM` de `cryptography.hazmat.primitives.ciphers.aead`; `decrypt(ciphertext_with_tag, nonce, key, envelope_meta) -> bytes`; todos los tests T006 deben pasar
- [X] T008 Escribir tests de serialización en `tests/unit/test_models.py`: `EntryRecord` roundtrip `to_dict`/`from_dict`, UUID generado en creación, `created_at` invariante, `updated_at` actualizado; `FolderRecord` roundtrip; `VaultPayload` roundtrip con entradas y carpetas; `VaultSession.derived_key` se sobreescribe con ceros al llamar a `zero_key()`
- [X] T009 Implementar `src/vault/models.py` — dataclasses `EntryRecord`, `FolderRecord`, `VaultPayload`, `VaultSession` con métodos `to_dict()` / `from_dict()`; `EntryRecord` genera UUID4 e ISO-8601 UTC en creación; `VaultSession.zero_key()` sobreescribe `derived_key` con ceros; todos los tests T008 deben pasar
- [X] T010 Implementar `src/vault/repository.py` — `load_vault_file(path: Path) -> dict` (lee y parsea JSON, valida campos obligatorios y tamaños de `salt`/`nonce`, lanza `VaultCorruptError`); `save_vault_file(path: Path, data: dict) -> None` (escritura atómica: `tempfile.NamedTemporaryFile` + `os.replace` en mismo filesystem)
- [X] T011 Escribir tests de tamper detection en `tests/integration/test_tamper_detection.py`: crear vault real → flip byte en `ciphertext` → `VaultCorruptError`; truncar `ciphertext` → `VaultCorruptError`; modificar `kdf_params.memory_cost` → `VaultCorruptError`; modificar `salt` → `WrongPasswordError`; eliminar campo `nonce` → `VaultCorruptError`; JSON malformado → `VaultCorruptError`

**Checkpoint**: Fundación completa — cobertura `src/crypto/` ≥ 95 %. Implementación de historias de usuario puede comenzar.

---

## Phase 3: User Story 1 — Crear una Bóveda Nueva y Desbloquearla (Priority: P1) 🎯 MVP

**Goal**: El usuario puede crear una bóveda cifrada nueva y desbloquearla con la contraseña maestra en sesiones posteriores.

**Independent Test**: Crear vault vacío → cerrar app → reabrir → desbloquear → bóveda accesible. Contraseña incorrecta → acceso denegado.

- [X] T012 [US1] Implementar `VaultService.__init__`, `create_vault()`, `unlock_vault()`, `lock_vault()`, propiedad `is_unlocked` en `src/vault/service.py`; `create_vault` genera salt + nonce, deriva clave, cifra payload vacío, escribe con `repository.save_vault_file()`; `unlock_vault` carga archivo, valida campos, deriva clave, descifra, crea `VaultSession`; `lock_vault` llama a `VaultSession.zero_key()`, descarta sesión
- [X] T013 [US1] Escribir tests del ciclo de vida de `VaultService` en `tests/unit/test_vault_service.py`: `create_vault` → `is_unlocked` True; `unlock_vault` correcta → True; `unlock_vault` con contraseña errónea → `WrongPasswordError`; `lock_vault` → `is_unlocked` False; `lock_vault` idempotente; `create_vault` en path existente → `VaultAlreadyExistsError`; archivo corrupto → `VaultCorruptError`
- [X] T014 [US1] Escribir test de integración roundtrip en `tests/integration/test_vault_roundtrip.py`: `create_vault` → verificar archivo en disco es JSON con campos correctos sin texto plano sensible → `lock_vault` → `unlock_vault` con contraseña correcta → `is_unlocked` True; `unlock_vault` con contraseña incorrecta → `WrongPasswordError`
- [X] T015 [P] [US1] Implementar `src/ui/views/create_vault_view.py` — frame Tkinter: botón "Elegir ubicación" (asksaveasfilename), campo contraseña + confirmación, advertencia prominente sobre recuperación imposible (Label en rojo), checkbox confirmación de advertencia, botón "Crear bóveda" (deshabilitado hasta confirmar advertencia); llama a `VaultService.create_vault()` y navega a `main_view` en éxito
- [X] T016 [P] [US1] Implementar `src/ui/views/unlock_view.py` — frame Tkinter: botón "Abrir bóveda" (askopenfilename, extensión `.vault`), campo contraseña, botón "Desbloquear", Label de error en rojo para `WrongPasswordError` / `VaultCorruptError`, enlace "Crear nueva bóveda" navega a `create_vault_view`; `<Return>` en campo contraseña dispara desbloqueo
- [X] T017 [US1] Implementar `src/ui/app.py` — clase `App(tk.Frame)`: gestión de ventana principal (`title`, `minsize`), método `show_view(view_class)` para navegar entre vistas; muestra `unlock_view` al inicio (o `create_vault_view` si no hay vault reciente); botón "Bloquear" en barra superior llama a `lock_vault()` + muestra `unlock_view`; inyecta `VaultService` a las vistas
- [X] T018 [US1] Implementar `src/main.py` — entry point: instancia `tk.Tk()`, configura título e icono, instancia `App(root, VaultService())`, llama `root.mainloop()`

---

## Phase 4: User Story 2 — Gestionar Entradas de Credenciales (Priority: P2)

**Goal**: El usuario puede agregar, ver, editar y eliminar entradas de credenciales con persistencia.

**Independent Test**: Con bóveda vacía, agregar 3 entradas → editar una → eliminar otra → bloquear → desbloquear → verificar estado persiste.

- [X] T019 [US2] Implementar `VaultService.get_entries()`, `add_entry()`, `update_entry()`, `delete_entry()` en `src/vault/service.py`; `add_entry` genera `EntryRecord` con UUID + timestamps, lanza `ValueError` si `title` vacío, lanza `FolderNotFoundError` si `folder_id` inválido; `update_entry` actualiza `updated_at` y guarda vault; `delete_entry` lanza `EntryNotFoundError` si no existe
- [X] T020 [US2] Extender tests en `tests/unit/test_vault_service.py`: `add_entry` devuelve `EntryRecord` con UUID; `update_entry` cambia campo y `updated_at`; `delete_entry` elimina entrada; `delete_entry` ID inexistente → `EntryNotFoundError`; `add_entry` con `folder_id` inválido → `FolderNotFoundError`; cambios persisten tras `lock_vault` + `unlock_vault`; `add_entry` con `title` vacío → `ValueError`
- [X] T021 [US2] Implementar `src/ui/views/entry_form_view.py` — Toplevel Tkinter: campos `title` (obligatorio, Label rojo si vacío), `username`, `password` (Entry con `show="*"`, botón ojo toggle), `url`, `notes` (Text widget multi-línea), selector de carpeta (OptionMenu poblado por `get_folders()`); botón "Guardar" llama a `add_entry()` o `update_entry()`; botón "Cancelar" cierra sin guardar
- [X] T022 [US2] Implementar lista de entradas y panel de detalle en `src/ui/views/main_view.py` — Treeview con columnas (Título, Usuario); doble clic abre `entry_form_view` en modo edición; botón "Nueva entrada" abre `entry_form_view` en modo creación; botón "Eliminar" con `messagebox.askyesno` de confirmación; refresca lista tras cada operación CRUD

---

## Phase 5: User Story 3 — Buscar Entradas en Tiempo Real (Priority: P3)

**Goal**: El campo de búsqueda filtra la lista de entradas con cada pulsación de tecla (≤ 100 ms incluso con 500 entradas).

**Independent Test**: Bóveda con 20+ entradas — escribir término → lista se filtra instantáneamente; borrar → lista completa; término sin resultados → estado vacío.

- [X] T023 [US3] Implementar `VaultService.search_entries()` en `src/vault/service.py` — búsqueda case-insensitive por subcadena en `title` y `username`; devuelve lista vacía si no hay coincidencias; lanza `VaultLockedError` si vault bloqueada
- [X] T024 [US3] Extender tests en `tests/unit/test_vault_service.py`: coincidencia por subcadena en `title`; coincidencia por subcadena en `username`; insensible a mayúsculas; query vacío devuelve todas las entradas de la vista activa; sin coincidencias devuelve lista vacía; búsqueda sobre 500 entradas completa en ≤ 100 ms (assert `time.perf_counter`)
- [X] T025 [P] [US3] Añadir barra de búsqueda a `src/ui/views/main_view.py` — `tk.Entry` con `StringVar`; trazar `StringVar` con `trace_add("write", callback)`; callback llama a `search_entries(query)` si `query` no vacío, o `get_entries()` si vacío; actualiza Treeview en cada pulsación; muestra Label "Sin resultados" cuando la lista devuelta está vacía

---

## Phase 6: User Story 4 — Generar Contraseñas Aleatorias Seguras (Priority: P4)

**Goal**: El generador produce contraseñas con longitud y conjuntos de caracteres configurables, insertándolas directamente en el campo contraseña del formulario.

**Independent Test**: Invocar generador → configurar longitud 24 + solo minúsculas + dígitos → generar → resultado tiene 24 chars y solo minúsculas/dígitos → regenerar → nuevo valor distinto → "Usar contraseña" → campo relleno.

- [X] T026 [US4] Implementar `src/generator/password_generator.py` — `generate_password(length, use_uppercase, use_lowercase, use_digits, use_symbols) -> str` usando `secrets.choice`; valida `8 <= length <= 128` y al menos un charset activo, lanza `ValueError` en caso contrario; nunca usa `random`
- [X] T027 [US4] Escribir tests en `tests/unit/test_password_generator.py`: longitud correcta; solo chars de charsets habilitados; valores sucesivos distintos (≥ 99/100 llamadas únicas sobre muestra de 100); boundary `length=8` y `length=128`; `ValueError` en `length=7`, `length=129`; `ValueError` con todos charsets False; un solo charset habilitado funciona sin error
- [X] T028 [P] [US4] Implementar `src/ui/views/generator_dialog.py` — `Toplevel` Tkinter: `Spinbox` para longitud (8–128), cuatro `Checkbutton` para charsets (al menos uno debe estar activo), botón "Generar" (deshabilitado si ningún charset activo), `Entry` readonly para resultado, botón "Regenerar", botón "Usar esta contraseña" que escribe valor en campo del caller y cierra; añadir botón "Generar contraseña" en `entry_form_view.py` que abre este diálogo

---

## Phase 7: User Story 5 — Copiar Credenciales al Portapapeles con Borrado Automático (Priority: P5)

**Goal**: Copiar usuario/contraseña al portapapeles con un clic; portapapeles se limpia automáticamente a los 20 s y al bloquear.

**Independent Test**: Copiar contraseña → pegar en editor → correcto → esperar 20 s → portapapeles vacío. Copiar → bloquear antes de 20 s → portapapeles inmediatamente vacío.

- [X] T029 [US5] Implementar `src/ui/clipboard.py` — variable de módulo `_timer: threading.Timer | None`; `copy_to_clipboard(root: tk.Tk, value: str, clear_after_s: int = 20)`: cancela timer previo, `root.clipboard_clear()` + `root.clipboard_append(value)`, inicia nuevo `threading.Timer(clear_after_s, _do_clear, args=[root])`; `cancel_clipboard_timer(root)`: cancela timer activo y llama a `root.clipboard_clear()` inmediatamente (FR-022)
- [X] T030 [P] [US5] Añadir botones "Copiar usuario" y "Copiar contraseña" a cada fila de entrada en `src/ui/views/main_view.py`; wired a `clipboard.copy_to_clipboard()`; mostrar confirmación visual transitoria (Label que desaparece tras 2 s); conectar `App.lock_vault()` para llamar a `clipboard.cancel_clipboard_timer()` antes de bloquear (FR-022)

---

## Phase 8: User Story 6 — Organizar Entradas en Carpetas (Priority: P6)

**Goal**: El usuario puede crear carpetas, asignar entradas a carpetas y navegar para ver solo las entradas de una carpeta.

**Independent Test**: Crear 2 carpetas → mover entradas → seleccionar carpeta → solo entradas de esa carpeta visibles → eliminar carpeta → entradas en "Sin carpeta".

- [X] T031 [US6] Implementar `VaultService.get_folders()`, `add_folder()`, `delete_folder()` en `src/vault/service.py`; `add_folder` lanza `DuplicateFolderNameError` si nombre duplicado, `ValueError` si nombre vacío o > 255 chars; `delete_folder` asigna `folder_id=None` a entradas afectadas y guarda vault, lanza `FolderNotFoundError` si no existe, devuelve count de entradas movidas
- [X] T032 [US6] Extender tests en `tests/unit/test_vault_service.py`: `add_folder` persiste y devuelve `FolderRecord`; nombre duplicado → `DuplicateFolderNameError`; `delete_folder` mueve entradas a `folder_id=None` y devuelve count correcto; `delete_folder` carpeta inexistente → `FolderNotFoundError`; carpeta vacía se elimina sin error; entradas en carpeta eliminada accesibles via `get_entries()` con `folder_id=None`
- [X] T033 [US6] Añadir panel lateral de carpetas a `src/ui/views/main_view.py` — `Listbox` con ítems "Todas las entradas", "Sin carpeta" y nombres de carpetas; seleccionar ítem filtra la lista de entradas mediante `get_entries(folder_id=...)`; botón "Nueva carpeta" usa `simpledialog.askstring`; botón "Eliminar carpeta" con `messagebox.askyesno` informando cuántas entradas pasan a "Sin carpeta"
- [X] T034 [P] [US6] Poblar selector de carpeta en `src/ui/views/entry_form_view.py` con `get_folders()`; incluir opción "Sin carpeta" (valor `None`); preseleccionar carpeta activa si se abre desde una vista de carpeta

---

## Phase 9: User Story 7 — Auto-bloqueo por Inactividad (Priority: P7)

**Goal**: La bóveda se bloquea automáticamente tras el período de inactividad configurado (default 5 min).

**Independent Test**: Configurar timeout a 10 s → desbloquear → no interactuar → tras 10 s pantalla de desbloqueo aparece. Interactuar antes de 10 s → timer se reinicia.

- [X] T035 [US7] Añadir timer de inactividad a `VaultService` en `src/vault/service.py` — atributo `_inactivity_timer: threading.Timer | None`; `record_activity()` cancela y reinicia timer con `timeout_s` (default 300); `lock_vault()` cancela timer; `__init__` acepta `auto_lock_timeout_s: int = 300`; cuando el timer dispara llama a `lock_vault()` y notifica a un callback `on_auto_lock` registrable
- [X] T036 [US7] Extender tests en `tests/unit/test_vault_service.py`: vault se bloquea tras timeout configurable (usar timeout pequeño, ≥ 0.1 s en test); `record_activity()` reinicia el timer (vault no se bloquea si se llama dentro del timeout); `lock_vault()` cancela el timer pendiente; `is_unlocked` False tras auto-lock
- [X] T037 [US7] Conectar `record_activity()` en `src/ui/app.py` — `root.bind_all("<KeyPress>", ...)`, `root.bind_all("<ButtonPress>", ...)`, `root.bind_all("<MouseWheel>", ...)`; en `on_auto_lock` callback: llamar a `show_view(UnlockView)` en el hilo de Tkinter usando `root.after(0, ...)`

---

## Phase 10: Polish & Cross-Cutting Concerns

**Propósito**: Configuración de usuario, cobertura final y validación de requisitos no funcionales

- [ ] T038 [P] Implementar `AppSettings` en `src/vault/models.py` — dataclass con `clipboard_timeout_s: int = 20` y `auto_lock_timeout_s: int = 300`; `load_settings(config_path: Path) -> AppSettings` y `save_settings(config_path, settings)` como JSON no sensible en directorio de configuración del usuario (`platformdirs` o `~/.config/vault-manager/settings.json`)
- [ ] T039 [P] Añadir diálogo de configuración en `src/ui/app.py` — `Toplevel` accesible desde menú "Configuración"; `Spinbox` para timeout de portapapeles (5–300 s); `Spinbox` para auto-bloqueo (60–3600 s); botón "Guardar" persiste `AppSettings`, actualiza `VaultService` con nuevos timeouts
- [ ] T040 Ejecutar suite completa de tests con `pytest --cov=src/crypto --cov-report=term-missing tests/` y verificar cobertura ≥ 95 % en `src/crypto/`; identificar y corregir cualquier brecha de cobertura en `src/crypto/kdf.py` y `src/crypto/vault_cipher.py`
- [ ] T041 [P] Validar requisitos no funcionales: verificar cero tráfico de red durante sesión completa (`ss -tp | grep python`); verificar escritura atómica del vault (matar proceso durante guardado → archivo anterior intacto); confirmar los 5 edge cases de spec.md están cubiertos por tests existentes

---

## Dependency Graph — Orden de Compleción de Historias

```
Phase 1 (Setup)
    └─→ Phase 2 (Foundation — crypto + models) — BLOQUEANTE para todo lo demás
             └─→ Phase 3 (US1: Vault lifecycle)  ← MVP mínimo entregable
                      └─→ Phase 4 (US2: CRUD entradas)
                      |        └─→ Phase 5 (US3: Búsqueda)
                      |        └─→ Phase 6 (US4: Generador)  ← puede hacerse en paralelo con US3
                      |        └─→ Phase 7 (US5: Portapapeles) ← puede hacerse en paralelo con US3/US4
                      |        └─→ Phase 8 (US6: Carpetas)
                      └─→ Phase 9 (US7: Auto-bloqueo) ← puede hacerse en paralelo con US2-US6
                               └─→ Phase 10 (Polish)
```

**Historias independientes entre sí** (una vez US2 completada):
- US3, US4, US5 pueden implementarse en cualquier orden entre ellas.
- US6 depende de US2 (entries tienen `folder_id`).
- US7 depende de US1 (necesita `lock_vault`).

---

## Ejemplos de Ejecución en Paralelo

### Dentro de Phase 3 (US1)
Una vez T012 y T013 completados:
```
T015 (create_vault_view.py)  ← paralelo
T016 (unlock_view.py)        ← paralelo
                             → T017 (app.py) ← requiere ambas vistas
                                     → T018 (main.py)
```

### Dentro de Phase 2 (Foundation)
```
T004 → T005 (kdf.py)     ←─ secuencial (TDD)
T006 → T007 (cipher.py)  ←─ secuencial (TDD)  ambas ramas en paralelo entre sí
T008 → T009 (models.py)  ←─ secuencial (TDD)
T010 (repository.py)     ←─ puede empezar tras T009
T011 (tamper tests)      ←─ requiere T005 + T007 + T009 + T010
```

### Dentro de Phase 4 (US2) y sus fases hermanas
```
T019 → T020 → T021 → T022  ← US2 completa
                            → T023 → T024 → T025  ← US3 (paralelo con US4, US5)
                            → T026 → T027 → T028  ← US4 (paralelo con US3, US5)
                            → T029 → T030          ← US5 (paralelo con US3, US4)
                            → T031 → T032 → T033 → T034  ← US6
                            → T035 → T036 → T037   ← US7 (puede iniciar antes que US2)
```

---

## Estrategia de Implementación

**MVP (Fases 1–3, T001–T018)**: Proyecto funcional con vault cifrado, creación, bloqueo y
desbloqueo. Todas las garantías de seguridad de la Constitución cumplidas desde el primer
entregable. Demuestra valor inmediato y base segura para todo lo demás.

**Incremento 1 (+ Fase 4, T019–T022)**: Gestor de contraseñas básico completo con CRUD.

**Incremento 2 (+ Fases 5–7, T023–T030)**: Usabilidad diaria: búsqueda, generador, portapapeles.

**Incremento 3 (+ Fases 8–9, T031–T037)**: Organización y seguridad adicional: carpetas y
auto-bloqueo.

**Release v1 (+ Fase 10, T038–T041)**: Configuración de usuario, cobertura validada y
certificación de requisitos no funcionales.
