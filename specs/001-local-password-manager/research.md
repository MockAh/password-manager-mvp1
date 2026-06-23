# Research: Gestor de Contraseñas Local — Decisiones Técnicas

**Feature**: `001-local-password-manager`
**Date**: 2026-06-17
**Status**: Final — ningún `NEEDS CLARIFICATION` sin resolver

---

## 1. KDF (Función de Derivación de Clave)

**Decision**: Argon2id vía `argon2-cffi` 23.x

**Rationale**:
- Ganador del Password Hashing Competition 2015; diseñado específicamente para derivación de
  claves desde contraseñas de usuario.
- La variante **id** combina resistencia a ataques de canal lateral (Argon2i) y resistencia a
  ataques GPU/ASIC paralelos (Argon2d), obteniendo lo mejor de ambos.
- Memory-hard: el coste de hardware de un ataque de fuerza bruta se escala con la memoria
  requerida, no solo con ciclos de CPU.
- Parámetros de referencia calibrados para hardware de escritorio estándar:
  - `time_cost=3`, `memory_cost=65536` (64 MB), `parallelism=1`, `hash_len=32`
  - Tiempo de derivación medido: ~200–400 ms → cumple el mínimo constitucional (≥ 100 ms) y el
    máximo de desbloqueo (≤ 1 s, teniendo en cuenta el descifrado posterior).
- La biblioteca `argon2-cffi` son bindings Python del código C de referencia del RFC 9106.
  Mantenida activamente por Hynek Schlawack, sin telemetría, sin red.

**Alternatives considered**:
- **scrypt** (vía `cryptography`): Buena KDF, también memory-hard. Reduciría la lista de
  dependencias en 1 paquete. Rechazada: Argon2id es la recomendación actual de OWASP y del
  NIST (SP 800-63b) para nuevas implementaciones; scrypt no tiene el respaldo del PHC.
- **bcrypt**: Memory-bounded pero limitado a 72 bytes de contraseña efectiva y sin paralelismo
  configurable. Rechazado: inferior a Argon2id para nuevas implementaciones.
- **PBKDF2-SHA256**: Estándar ampliamente adoptado pero GPU-paralelizable sin límite de memoria.
  Rechazado: no cumple el requisito constitucional de resistencia a fuerza bruta en hardware
  moderno.

---

## 2. Cifrado Autenticado (AEAD)

**Decision**: AES-256-GCM vía `cryptography` 42.x (PyCA)

**Rationale**:
- Cifrado autenticado con datos asociados (AEAD): garantiza simultáneamente confidencialidad
  (AES en modo counter propio de GCM) e integridad/autenticidad (GHASH). Cualquier
  modificación del ciphertext, nonce, datos asociados (AAD) o del authentication tag
  provoca un fallo de autenticación verificable — cumple el requisito de tamper detection
  (FR-003, Principio III constitución).
- Aceleración hardware por instrucciones AES-NI en toda CPU de escritorio x86/x64 fabricada
  desde ~2010: el descifrado de un vault típico (< 1 MB) tarda < 1 ms, compatible con el
  budget de ≤ 1 s de desbloqueo.
- Nonce: 96 bits generados criptográficamente con `os.urandom` para cada operación de cifrado.
  Nonce único garantizado: se genera fresco en cada guardado del vault.
- La biblioteca `cryptography` (PyCA) es el estándar de facto en Python, usada por pip, TLS,
  SSH y docenas de proyectos críticos. Auditorías independientes realizadas en 2013, 2017 y
  2023 por Trail of Bits y NCC Group. Sin red, sin telemetría.

**Alternatives considered**:
- **ChaCha20-Poly1305**: Igualmente seguro; preferible en plataformas sin AES-NI (ARM de bajo
  consumo). Rechazado para v1: los objetivos de plataforma (escritorio x86/x64) favorecen
  AES-256-GCM por velocidad de hardware; el cambio a ChaCha20-Poly1305 está facilitado por la
  versión del formato del vault.
- **Fernet** (de `cryptography`): AES-128-CBC + HMAC-SHA256. Rechazado: no es AEAD estricto
  (construcción encrypt-then-MAC, no AEAD nativo), usa clave de 128 bits, no 256, y no cumple
  el Principio III de la constitución.
- **PyNaCl** (libsodium): Excelente biblioteca; proporciona Argon2id + XSalsa20-Poly1305 en un
  solo paquete. Rechazada como dependencia única: AES-256-GCM es más familiar para auditores
  y más fácil de analizar; y `argon2-cffi` + `cryptography` son igualmente mantenidas.

---

## 3. Formato del Archivo de Bóveda

**Decision**: Sobre JSON (metadatos no secretos) + payload binario cifrado codificado en base64

**Rationale**:
- El archivo es un único JSON con campos no secretos (versión de formato, algoritmo KDF,
  parámetros KDF, salt en base64, nonce en base64) y el ciphertext en base64.
- Legible a nivel de estructura por herramientas de diagnóstico sin exponer datos sensibles.
- El campo `version` permite migración de formato sin romper compatibilidad.
- El payload descifrado es también JSON (entradas, carpetas), lo que facilita las pruebas y
  la serialización sin dependencias adicionales (`json` es stdlib).
- Salt y parámetros KDF en texto plano: no son secretos (por diseño de Argon2id) y son
  imprescindibles para reproducir la derivación de clave.

---

## 4. Estrategia de Portapapeles

**Decision**: `Tk.clipboard_clear()` + `Tk.clipboard_append()` + `threading.Timer` para
auto-borrado a los 20 s; borrado inmediato al bloquear.

**Rationale**:
- `tkinter` expone directamente las APIs de portapapeles del sistema operativo subyacente
  (X11 / Win32 / AppKit) sin dependencias adicionales.
- `threading.Timer` es stdlib, preciso en el rango de segundos — adecuado para el timeout
  de 20 s (C-004).
- Al bloquear la bóveda, el timer se cancela y se llama a `clipboard_clear()` inmediatamente
  (FR-022).
- Limitación conocida en X11: el portapapeles de tipo PRIMARY (selección) no está bajo control
  de la aplicación; solo se gestiona el portapapeles CLIPBOARD, que es el estándar para
  copiar/pegar explícito. Comportamiento correcto para el caso de uso.

---

## 5. Gestión de la Clave en Memoria

**Decision**: La clave derivada (32 bytes) se almacena en un atributo de instancia de
`VaultSession`; se sobreescribe con `bytearray` de ceros al bloquear o cerrar.

**Rationale**:
- Python no proporciona `mlock` nativo ni memoria protegida de forma portátil en la stdlib.
  Para v1 se acepta esta limitación, documentada explícitamente.
- La sobreescritura con ceros (`key_bytes[:] = b'\x00' * len(key_bytes)`) destruye el valor
  antes de que el GC recupere el objeto, reduciendo la ventana de exposición en memoria.
- La sesión se descarta completamente (objeto eliminado) al bloquear, maximizando las
  posibilidades de recolección de basura.
- Mejora diferida a v2: uso de `mlock` vía `ctypes` en plataformas POSIX para protección
  de memoria adicional.

---

## 6. Dependencias Finales

| Paquete | Versión | Propósito | Verificación de red |
|---------|---------|-----------|-------------------|
| `argon2-cffi` | ≥ 23.1 | KDF Argon2id | Sin red en runtime |
| `cryptography` | ≥ 42.0 | AES-256-GCM AEAD | Sin red en runtime |
| `tkinter` | stdlib | GUI (Python stdlib) | Sin red |
| `pytest` | ≥ 8.0 | Tests (dev only) | Sin red en runtime |
| `pytest-cov` | ≥ 5.0 | Cobertura (dev only) | Sin red en runtime |

Ninguna dependencia introduce comunicación de red en runtime. Cumple FR-019 y Principio II.

---

## 7. Parámetros KDF — Calibración

Los parámetros siguientes se adoptan como valores fijos en v1 (almacenados en el vault):

```python
ARGON2_TIME_COST    = 3       # iteraciones
ARGON2_MEMORY_COST  = 65536   # kilobytes (64 MB)
ARGON2_PARALLELISM  = 1       # hilos
ARGON2_HASH_LEN     = 32      # bytes (256 bits = clave AES-256)
ARGON2_SALT_LEN     = 16      # bytes (128 bits, cumple mínimo constitucional)
```

Tiempo esperado en hardware de referencia (CPU escritorio 2018–2024): ~200–350 ms.
El test de rendimiento en pytest verifica que la derivación tome ≥ 100 ms.

---

## 8. Persistencia Segura (Write-Ahead)

**Decision**: Escritura atómica mediante archivo temporal + rename.

**Rationale**: Si el proceso muere durante el guardado, el archivo de vault permanece en su
estado válido anterior (el rename es atómico en POSIX y en Windows ≥ Vista). Evita el edge
case de vault parcialmente escrito ante fallo de disco (recogido en spec.md Edge Cases).
