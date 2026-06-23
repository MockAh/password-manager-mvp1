# Implementation Plan: Gestor de Contraseñas Local y Offline

**Branch**: `001-local-password-manager` | **Date**: 2026-06-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-local-password-manager/spec.md`

## Summary

Aplicación de escritorio Python con interfaz Tkinter que almacena credenciales en un único
archivo cifrado con AES-256-GCM, con clave derivada mediante Argon2id. Implementa las historias
P1–P7: creación y desbloqueo de bóveda, gestión CRUD de entradas, búsqueda en tiempo real,
generador de contraseñas configurable, copia al portapapeles con auto-borrado a los 20 s,
organización por carpetas y auto-bloqueo por inactividad a los 5 min. La arquitectura separa
estrictamente el núcleo criptográfico/datos de la capa Tkinter.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- `argon2-cffi` ≥ 23.1 — KDF Argon2id (derivación de clave resistente a fuerza bruta)
- `cryptography` ≥ 42.0 (PyCA) — AES-256-GCM AEAD (cifrado autenticado)
- `tkinter` — GUI (stdlib Python, sin dependencias gráficas externas)
- `pytest` ≥ 8.0 + `pytest-cov` ≥ 5.0 — tests y cobertura (dev)

**Storage**: Un único archivo cifrado en disco local (formato JSON; ver `contracts/vault-file-format.md`)

**Testing**: pytest; cobertura ≥ 95 % en `src/crypto/`; sin mocking de primitivas criptográficas

**Target Platform**: Escritorio — Linux, macOS, Windows — con Python 3.11+ instalado

**Project Type**: Desktop GUI application (aplicación de escritorio con interfaz gráfica)

**Performance Goals**:
- Desbloqueo de bóveda (KDF Argon2id + AES-256-GCM descifrado): ≤ 1 s
- Búsqueda y filtrado de entradas: ≤ 100 ms (incluso con 500 entradas)
- Copia al portapapeles: ≤ 50 ms

**Constraints**:
- 100 % offline; cero dependencias de red en runtime (FR-019, Principio II)
- Clave derivada solo en memoria; nunca escrita en disco (FR-006)
- Datos sensibles descifrados nunca escritos en disco fuera del vault cifrado (FR-007)
- Primitivas criptográficas solo a través de `argon2-cffi` y `cryptography`; ninguna implementación propia
- Escritura atómica del vault (archivo temporal + rename) para tolerancia a fallos de disco

**Scale/Scope**: 1 usuario, 1 bóveda activa por sesión, hasta 500+ entradas sin degradación perceptible

## Constitution Check

*GATE: Verificado antes de Phase 0 research y re-verificado tras Phase 1 design.*

| Principio | Gate | Estado |
|-----------|------|--------|
| **I — Seguridad por Diseño** | Toda operación de acceso requiere contraseña maestra. Clave solo en memoria. Rechazo explícito ante contraseña incorrecta (FR-009). | ✅ PASA |
| **II — Privacidad Absoluta / Offline** | Cero dependencias de red en runtime. `argon2-cffi` y `cryptography` no tienen telemetría ni red. FR-019. | ✅ PASA |
| **III — Cifrado Autenticado + KDF** | AES-256-GCM (AEAD) + Argon2id con salt único de 16 bytes. Parámetros KDF almacenados en vault (no secretos). Clave de 256 bits. FR-003, FR-004, FR-005. | ✅ PASA |
| **IV — Sin Recuperación de Contraseña Maestra** | Ningún mecanismo de recuperación implementado. Advertencia prominente al crear vault. FR-020, FR-021. | ✅ PASA |
| **V — Calidad de Código** | Módulo `src/crypto/` aislado, expone interfaz de alto nivel. Resto del código no llama directamente a primitivas. Módulos ≤ 400 líneas. | ✅ PASA |
| **VI — Pruebas Automatizadas de Seguridad** | Tests obligatorios: cifrado/descifrado, contraseña incorrecta, tamper detection, corrupción de vault, unicidad de salt/nonce. Cobertura ≥ 95 % en `src/crypto/`. | ✅ PASA |
| **VII — Consistencia UX** | Confirmación explícita para eliminar entradas y carpetas. Bloqueo manual disponible. Auto-bloqueo y borrado automático de portapapeles. Idioma: español (C-006). | ✅ PASA |
| **VIII — Rendimiento** | Parámetros Argon2id calibrados para ≥ 100 ms y ≤ 1 s. Búsqueda filtrada en memoria (sin I/O). Operaciones de UI no bloquean la derivación de clave. | ✅ PASA |

**Resultado**: Todos los gates pasan. No hay violaciones. Fase de diseño autorizada.

## Project Structure

### Documentation (this feature)

```text
specs/001-local-password-manager/
├── plan.md              # Este archivo
├── research.md          # Decisiones criptográficas y técnicas (Phase 0)
├── data-model.md        # Modelo de datos (Phase 1)
├── quickstart.md        # Guía de validación (Phase 1)
├── contracts/           # Interfaces públicas (Phase 1)
│   ├── vault-file-format.md
│   └── vault-service-interface.md
└── tasks.md             # Tareas de implementación (generado por /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── crypto/
│   ├── __init__.py          # Exporta la API pública del módulo crypto
│   ├── kdf.py               # Derivación Argon2id: derive_key(), verify_params()
│   └── vault_cipher.py      # Cifrado/descifrado AES-256-GCM: encrypt(), decrypt()
├── vault/
│   ├── __init__.py
│   ├── models.py            # Dataclasses: Vault, Entry, Folder, VaultSession
│   ├── repository.py        # Persistencia: load_vault_file(), save_vault_file() — escritura atómica
│   └── service.py           # VaultService: lógica de negocio, sin acoplamiento a UI
├── generator/
│   ├── __init__.py
│   └── password_generator.py  # generate_password(length, charset_flags) — solo stdlib secrets
├── ui/
│   ├── __init__.py
│   ├── app.py               # Clase App: gestión de ventana principal y navegación entre vistas
│   ├── clipboard.py         # copy_to_clipboard(value, timeout_s): copia + timer de borrado
│   └── views/
│       ├── __init__.py
│       ├── create_vault_view.py   # Vista: crear nueva bóveda
│       ├── unlock_view.py         # Vista: desbloquear bóveda existente
│       ├── main_view.py           # Vista: lista de entradas, búsqueda, carpetas, barra de acciones
│       ├── entry_form_view.py     # Vista: formulario crear/editar entrada
│       └── generator_dialog.py   # Diálogo: generador de contraseñas (invocado desde entry_form)
└── main.py                  # Entry point: arranca Tk, instancia App

tests/
├── unit/
│   ├── test_kdf.py              # Argon2id: derivación determinista, unicidad de salt, parámetros
│   ├── test_vault_cipher.py     # AES-256-GCM: roundtrip, contraseña incorrecta, tamper, corrupción
│   ├── test_models.py           # Dataclasses: serialización/deserialización JSON
│   ├── test_vault_service.py    # VaultService: CRUD entradas/carpetas, reglas de negocio
│   └── test_password_generator.py  # Generador: longitud, conjuntos, unicidad
└── integration/
    ├── test_vault_roundtrip.py      # Flujo completo: crear vault → bloquear → desbloquear → verificar
    └── test_tamper_detection.py     # Modificación de bytes en ciphertext/nonce/salt → rechazo

pyproject.toml       # Metadatos del proyecto, dependencias, configuración pytest y coverage
```

**Structure Decision**: Single project con separación estricta de capas. `src/crypto/` es el
módulo aislado auditeable; `src/ui/` es la capa delgada sin lógica de negocio. El resto del
código interactúa con `src/vault/service.py` sin conocer los detalles criptográficos.

## Complexity Tracking

> No hay violaciones constitucionales que justificar. Todos los gates pasan.
