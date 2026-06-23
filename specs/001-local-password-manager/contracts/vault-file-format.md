# Contrato: Formato del Archivo de Bóveda

**Versión de formato**: 1
**Feature**: `001-local-password-manager`
**Date**: 2026-06-17

Este documento describe el esquema del único archivo que persiste en disco.
El archivo es el contrato de durabilidad del sistema: si cambia su formato, la versión debe
incrementarse para permitir migración.

---

## Estructura del Archivo

El archivo de bóveda es un objeto JSON codificado en UTF-8 con los campos siguientes.
**Ningún campo contiene datos sensibles en texto plano.**

```json
{
  "version": 1,
  "kdf": "argon2id",
  "kdf_params": {
    "time_cost": 3,
    "memory_cost": 65536,
    "parallelism": 1,
    "hash_len": 32
  },
  "salt": "<base64url-standard, 16 bytes decodificados>",
  "nonce": "<base64url-standard, 12 bytes decodificados>",
  "ciphertext": "<base64url-standard, longitud variable>"
}
```

---

## Definición de Campos

| Campo | Tipo JSON | Descripción |
|-------|-----------|-------------|
| `version` | `number` (entero) | Versión del formato. Actualmente `1`. Cambios incompatibles incrementan este número. |
| `kdf` | `string` | Identificador del algoritmo KDF. Valor fijo en v1: `"argon2id"`. |
| `kdf_params` | `object` | Parámetros de la KDF necesarios para reproducir la derivación de clave. No son secretos. |
| `kdf_params.time_cost` | `number` | Número de iteraciones de Argon2id. |
| `kdf_params.memory_cost` | `number` | Coste de memoria en KiB. |
| `kdf_params.parallelism` | `number` | Número de hilos paralelos. |
| `kdf_params.hash_len` | `number` | Longitud del hash derivado en bytes. Debe ser `32` en v1. |
| `salt` | `string` | Salt aleatorio en base64 estándar. Decodificado: 16 bytes. Generado en la creación de la bóveda y nunca modificado. No es secreto. |
| `nonce` | `string` | Nonce AES-GCM en base64 estándar. Decodificado: 12 bytes. Generado de forma aleatoria en cada operación de guardado. |
| `ciphertext` | `string` | Payload cifrado en base64 estándar. Incluye el authentication tag GCM (16 bytes finales). El payload descifrado es el JSON de `VaultPayload` codificado en UTF-8. |

---

## Algoritmo de Cifrado y Autenticación

**KDF**: Argon2id (RFC 9106)
- Entrada: contraseña maestra (UTF-8) + `salt` (binario)
- Parámetros: `kdf_params`
- Salida: clave de 32 bytes (256 bits) — nunca almacenada

**AEAD**: AES-256-GCM
- Clave: 32 bytes derivados por Argon2id
- Nonce: 12 bytes (`nonce` del archivo)
- AAD (datos adicionales autenticados): JSON canónico (`sort_keys=True`, UTF-8) construido
  con los campos `version`, `kdf`, `kdf_params` y `salt` del envelope — en ese orden y con
  los mismos valores leídos del archivo. El AAD DEBE ser idéntico al cifrar y al descifrar.
  **Motivo**: impedir ataques de downgrade de parámetros KDF. Un atacante que reduzca
  `kdf_params.memory_cost` para facilitar fuerza bruta causará un fallo `InvalidTag`
  inmediato al intentar descifrar, porque el AAD calculado no coincidirá con el usado
  al cifrar.
- Salida: ciphertext + 16-byte authentication tag (concatenados)

**Consecuencia de integridad**: si cualquier byte del `ciphertext`, `nonce`, `salt` o
cualquier campo del envelope incluido en el AAD (`version`, `kdf`, `kdf_params`) se
modifica externamente, la operación `decrypt()` lanza `InvalidTag` y el vault se rechaza.

---

## Payload Descifrado (VaultPayload)

El resultado del descifrado es el JSON de `VaultPayload` (ver [data-model.md](../data-model.md)).
**Este JSON nunca se escribe en disco.**

---

## Reglas de Validación al Abrir el Archivo

Un lector DEBE rechazar el archivo con error claro en los siguientes casos:

1. El JSON no es válido o falta algún campo obligatorio.
2. `version` ≠ `1` (versión no soportada).
3. `kdf` ≠ `"argon2id"` (algoritmo no soportado).
4. `salt` decodificado ≠ 16 bytes.
5. `nonce` decodificado ≠ 12 bytes.
6. `kdf_params.hash_len` ≠ 32.
7. El descifrado falla con `InvalidTag` (contraseña incorrecta o datos manipulados).

---

## Ejemplo Completo

```json
{
  "version": 1,
  "kdf": "argon2id",
  "kdf_params": {
    "time_cost": 3,
    "memory_cost": 65536,
    "parallelism": 1,
    "hash_len": 32
  },
  "salt": "dGVzdHNhbHQxMjM0NTY=",
  "nonce": "dGVzdG5vbmNlMQ==",
  "ciphertext": "R2VuZXJhdGVkQnlBRVMtMjU2LUNNTQ=="
}
```

*(Los valores de `salt`, `nonce` y `ciphertext` son ilustrativos; en producción son binario aleatorio codificado en base64.)*

---

## Política de Migración de Versiones

- Cambios compatibles hacia atrás (nuevos campos opcionales): incremento MINOR del campo `version` no es necesario en v1; se documenta en `CHANGELOG`.
- Cambios incompatibles (nuevo KDF, nuevo algoritmo de cifrado, restructuración del payload): incremento del campo `version`. El código DEBE detectar versiones desconocidas y rechazar el archivo con un mensaje que indique la versión del software necesaria.
