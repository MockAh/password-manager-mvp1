<!--
Sync Impact Report
Version change: TEMPLATE (sin versión) → 1.0.0
Principios modificados: Todos (primera población real de la constitución desde la plantilla)
Secciones añadidas:
  - Core Principles (I–VIII): Seguridad por Diseño, Privacidad Absoluta y Operación Offline,
    Cifrado Autenticado y Derivación Robusta de Clave, Sin Recuperación de Contraseña Maestra,
    Calidad de Código, Pruebas Automatizadas de Seguridad, Consistencia UX, Rendimiento
  - Resolución de Conflictos entre Principios
  - Decisiones Técnicas Guiadas por la Constitución
  - Governance
Secciones eliminadas: N/A (placeholders de plantilla reemplazados)
Plantillas revisadas:
  - .specify/templates/plan-template.md ✅ revisado — "Constitution Check" aplica jerarquía de seguridad
  - .specify/templates/spec-template.md ✅ revisado — escenarios de aceptación alineados con principios
  - .specify/templates/tasks-template.md ✅ revisado — organización por fases soporta enfoque security-first
TODOs diferidos: Ninguno
-->

# Gestor de Contraseñas Local — Constitución

## Core Principles

### I. Seguridad por Diseño *(NON-NEGOTIABLE)*

La seguridad es el valor supremo de este proyecto. Toda decisión de diseño, arquitectura e
implementación DEBE analizarse desde la perspectiva de seguridad en primer lugar. Ante cualquier
conflicto entre seguridad y otra propiedad deseable (comodidad, rendimiento, velocidad de
desarrollo), la seguridad SIEMPRE prevalece.

- Los datos sensibles —contraseñas, notas, metadatos de entradas— NUNCA residen en disco sin cifrar.
- Las claves criptográficas NUNCA se almacenan en texto plano; su ciclo de vida en memoria DEBE
  ser mínimo y auditado.
- Todo acceso a la bóveda DEBE requerir autenticación con la contraseña maestra.
- Se aplica el principio de mínimo privilegio: ningún componente accede a más datos de los
  estrictamente necesarios para su función.
- Las superficies de ataque se reducen al mínimo: no se exponen APIs externas, no se cargan
  plugins de terceros sin revisión explícita de seguridad.

**Rationale**: Un gestor de contraseñas que falla en seguridad traiciona la confianza del usuario de
forma irreversible. El coste de un fallo de seguridad supera el coste de cualquier limitación
funcional.

### II. Privacidad Absoluta y Operación Offline *(NON-NEGOTIABLE)*

La aplicación funciona exclusivamente de forma local y offline. Los datos del usuario NUNCA salen
del dispositivo bajo ninguna circunstancia.

- Está estrictamente prohibida toda comunicación de red: sincronización en la nube, comprobación
  automática de actualizaciones, telemetría, informes de errores remotos y llamadas a servicios
  externos.
- No existe ningún mecanismo de "llamada a casa" ni análisis de uso.
- Los únicos datos escritos en disco son los archivos de la bóveda cifrada y la configuración local
  no sensible (e.g., preferencias de UI).
- Las dependencias de terceros DEBEN auditarse para verificar que no introducen comunicación de red
  implícita ni recolección de datos.

**Rationale**: La privacidad del usuario es absoluta. Ninguna característica o conveniencia justifica
exponer información sobre el uso de la aplicación o los datos almacenados.

### III. Cifrado Autenticado y Derivación Robusta de Clave *(NON-NEGOTIABLE)*

La bóveda DEBE protegerse con criptografía fuerte y correctamente implementada. No se permiten
atajos criptográficos.

- El cifrado de la bóveda DEBE usar cifrado autenticado con datos adicionales (AEAD): AES-256-GCM
  o ChaCha20-Poly1305. Queda prohibido el cifrado sin autenticación (e.g., AES-CBC sin MAC).
- La clave de cifrado DEBE derivarse de la contraseña maestra mediante una KDF resistente a fuerza
  bruta: Argon2id (preferido), scrypt o bcrypt. Los parámetros DEBEN calibrarse para que la
  derivación tome ≥ 100 ms en hardware de referencia.
- Cada bóveda DEBE usar un salt criptográficamente aleatorio único (mínimo 16 bytes) generado en
  su creación. El salt se almacena junto a la bóveda cifrada en texto plano (no es secreto).
- La clave derivada NUNCA se almacena en disco. DEBE residir solo en memoria durante la sesión
  activa y sobreescribirse con ceros al bloquear la bóveda o cerrar la aplicación.
- Los nonces/IVs para cada operación de cifrado DEBEN ser únicos y generados criptográficamente.
- Los parámetros KDF (algoritmo, coste de memoria, coste CPU, longitud de salt) se almacenan junto
  a la bóveda para permitir migración futura sin romper compatibilidad.
- Está prohibido el uso de algoritmos obsoletos o débiles: MD5, SHA-1, DES, 3DES, RC4, AES-ECB,
  RSA < 2048 bits.

**Rationale**: La criptografía correctamente implementada es la garantía técnica de la seguridad.
Cualquier atajo criptográfico invalida todas las demás protecciones del sistema.

### IV. Sin Recuperación de Contraseña Maestra *(NON-NEGOTIABLE)*

No existe ningún mecanismo de recuperación de la contraseña maestra. Esta limitación es
intencional, irrevocable y DEBE comunicarse de forma prominente al usuario.

- La aplicación NO DEBE implementar preguntas de seguridad, claves de recuperación almacenadas
  remotamente, ni ninguna forma de reset de contraseña maestra.
- Si el usuario olvida la contraseña maestra, los datos de la bóveda son irrecuperables. Este es
  el diseño correcto: cualquier mecanismo de recuperación introduce un vector de ataque equivalente.
- La interfaz de usuario DEBE advertir claramente de esta consecuencia durante la creación de la
  bóveda y en la documentación de usuario.
- Se puede ofrecer la exportación de un backup cifrado de la bóveda (responsabilidad del usuario),
  pero la clave de dicho backup DEBE derivarse igualmente de la contraseña maestra.

**Rationale**: Toda recuperación de credenciales implica que existe un secreto alternativo. Ese
secreto alternativo es el nuevo vector de ataque. La única garantía absoluta es la no existencia
de ningún mecanismo de recuperación.

### V. Calidad de Código — Legible, Modular y Revisable

El código DEBE ser comprensible por cualquier colaborador competente sin recurrir al autor original.
La auditabilidad es una propiedad de seguridad, no solo de mantenibilidad.

- Cada módulo tiene una responsabilidad única y bien delimitada (Single Responsibility Principle).
  Los límites del módulo criptográfico DEBEN ser especialmente claros y explícitos.
- Las funciones criptográficas DEBEN estar encapsuladas en un módulo dedicado (`crypto/` o
  equivalente) que exponga una interfaz de alto nivel. El resto del código NO llama directamente
  a primitivas criptográficas.
- El código DEBE ser revisable en pull/merge requests de tamaño razonable (< 400 líneas por PR
  salvo justificación documentada).
- Se prohíbe la lógica implícita o "magia" difícil de razonar: las decisiones de seguridad DEBEN
  ser explícitas y trazables en el código.
- La nomenclatura DEBE ser descriptiva; las abreviaciones crípticas están prohibidas en contextos
  de seguridad.

**Rationale**: El código que no se puede revisar no se puede auditar. La auditabilidad es una
propiedad de seguridad de primera clase.

### VI. Pruebas Automatizadas de Seguridad — Cobertura Obligatoria

Cada requisito de seguridad definido en esta Constitución DEBE tener al menos una prueba
automatizada que lo verifique de forma continua.

- Los vectores de ataque criptográficos DEBEN tener pruebas específicas: integridad del cifrado,
  rechazo de datos manipulados (tamper detection), unicidad de nonces y salts.
- Las rutas de acceso no autenticado DEBEN tener pruebas que confirmen su rechazo.
- Las pruebas de seguridad son OBLIGATORIAS y se ejecutan en cada verificación local y CI/CD antes
  de fusionar código. No existe excepción.
- Se aplica TDD para toda lógica de seguridad: la prueba se escribe antes de la implementación.
- Los tests de rendimiento de la KDF DEBEN verificar que el coste mínimo (≥ 100 ms) se mantiene
  ante cualquier refactorización.
- La cobertura de tests sobre el módulo `crypto/` DEBE ser ≥ 95 %.

**Rationale**: Lo que no se prueba no se garantiza. Las propiedades de seguridad DEBEN ser
verificables de forma continua, no solo en auditorías puntuales.

### VII. Consistencia de la Experiencia de Usuario

La interfaz de usuario DEBE ser predecible, coherente y libre de sorpresas. La inconsistencia en
la UX de un gestor de contraseñas tiene consecuencias de seguridad directas.

- Los patrones de interacción (desbloqueo, búsqueda, edición, copia al portapapeles) DEBEN ser
  consistentes en toda la aplicación.
- Los mensajes de error y las advertencias de seguridad DEBEN ser claros, concretos y en el idioma
  del usuario. Se prohíben los mensajes técnicos crípticos en la interfaz.
- Las acciones destructivas o de alto riesgo (eliminar entrada, cambiar contraseña maestra) DEBEN
  requerir confirmación explícita del usuario.
- El bloqueo automático de la bóveda por inactividad es obligatorio y configurable, con un valor
  por defecto seguro de ≤ 5 minutos.
- La copia de contraseñas al portapapeles DEBE limpiarse automáticamente, configurable por el
  usuario, con un valor por defecto de ≤ 30 segundos.

**Rationale**: Una UX inconsistente genera errores del usuario. Los errores del usuario en un
gestor de contraseñas tienen consecuencias de seguridad directas e inmediatas.

### VIII. Rendimiento en Operaciones Diarias

Las operaciones frecuentes DEBEN percibirse como instantáneas. Un gestor de contraseñas lento es
un gestor de contraseñas que el usuario abandona, lo que invalida su propósito de seguridad.

- Desbloqueo de la bóveda (derivación de clave + descifrado): DEBE completarse en ≤ 1 segundo en
  hardware de referencia; los parámetros KDF DEBEN calibrarse para satisfacer simultáneamente el
  coste mínimo (≥ 100 ms) y este límite superior.
- Búsqueda y filtrado de entradas en la bóveda: DEBE responder en ≤ 100 ms.
- Copia de credenciales al portapapeles: DEBE ejecutarse en ≤ 50 ms.
- Las operaciones de cifrado/descifrado NO DEBEN bloquear la UI; DEBEN ejecutarse en un
  hilo o proceso separado.
- Las optimizaciones de rendimiento que requieran reducir el coste de la KDF por debajo del mínimo
  garantizado (≥ 100 ms) quedan **prohibidas**.

**Rationale**: La adopción sostenida es condición necesaria para que la herramienta cumpla su
propósito. El rendimiento se optimiza siempre dentro de los límites de seguridad, nunca a su costa.

## Resolución de Conflictos entre Principios

Cuando dos principios colisionen en una decisión de diseño o implementación, se aplica la siguiente
jerarquía de forma estricta:

1. **Seguridad por Diseño** (Principio I) — Prioridad absoluta e irrevocable.
2. **Privacidad Absoluta y Operación Offline** (Principio II) — Nunca se negocia.
3. **Cifrado Autenticado y Derivación de Clave** (Principio III) — Los parámetros criptográficos no
   se degradan por conveniencia ni rendimiento.
4. **Sin Recuperación de Contraseña Maestra** (Principio IV) — Invariante del sistema, sin
   excepciones.
5. **Pruebas Automatizadas de Seguridad** (Principio VI) — Una feature sin tests de seguridad no se
   entrega.
6. **Calidad de Código** (Principio V) — La auditabilidad es una propiedad de seguridad.
7. **Consistencia UX** (Principio VII) — Subordinada a la seguridad; nunca la vulnera.
8. **Rendimiento** (Principio VIII) — Se optimiza dentro de los límites de seguridad, nunca a su
   costa.

**Regla de oro**: En caso de duda, la decisión que expone menos superficie de ataque es la correcta.

## Decisiones Técnicas Guiadas por la Constitución

Esta sección traduce los principios en directrices técnicas concretas para decisiones de
implementación:

**Selección de algoritmos criptográficos**: Solo se permiten algoritmos revisados por la comunidad
criptográfica con un historial de seguridad demostrado. Toda propuesta de cambio de algoritmo DEBE
incluir referencias a su revisión y justificación respecto al estado del arte.

**Gestión de la clave en memoria**: La clave derivada DEBE almacenarse en regiones de memoria
protegida (`mlock` en Unix, `SecureZeroMemory` en Windows, o equivalente del lenguaje elegido) y
sobreescribirse explícitamente con ceros al bloquear la bóveda o al cerrar la aplicación.

**Módulo criptográfico aislado**: El código criptográfico reside en un único módulo (`crypto/` o
equivalente), sin dependencias directas a la UI ni al almacenamiento. Esta separación es
obligatoria para facilitar la auditoría independiente y el reemplazo de primitivas.

**Evaluación de dependencias externas**: Se evalúa: mantenimiento activo, historial de
vulnerabilidades y ausencia de comunicación de red implícita. Se prefieren bibliotecas
criptográficas bien auditadas (e.g., libsodium, APIs criptográficas del sistema operativo) sobre
implementaciones propias de primitivas.

**Plan de revisión de seguridad**: Antes de cada release mayor se DEBE realizar una revisión del
módulo criptográfico. Los hallazgos se documentan y resuelven antes de publicar la release.

**Constitution Check en planes de feature**: Todo plan de implementación (`plan.md`) DEBE incluir
un bloque "Constitution Check" que verifique explícitamente el cumplimiento de los Principios I–IV
antes de iniciar la fase de diseño.

## Governance

Esta Constitución es el documento normativo supremo del proyecto. Ningún otro documento, práctica
de equipo o criterio de rendimiento puede anularla.

**Proceso de enmienda**:
- Los Principios I–IV (NON-NEGOTIABLE) requieren consenso explícito del equipo completo y
  documentación de la justificación de seguridad para cualquier enmienda.
- Los Principios V–VIII requieren revisión y aprobación de al menos un revisor adicional.
- Toda enmienda DEBE actualizar `LAST_AMENDED_DATE` e incrementar `CONSTITUTION_VERSION` según
  las reglas de versionado semántico definidas a continuación.

**Política de versionado**:
- MAJOR: Eliminación o redefinición de principios NON-NEGOTIABLE; cambios incompatibles en las
  garantías de seguridad del sistema.
- MINOR: Adición de nuevos principios o secciones; expansión material de principios existentes.
- PATCH: Clarificaciones, correcciones de redacción, refinamientos no semánticos.

**Revisión de cumplimiento**:
- El "Constitution Check" de `plan-template.md` se verifica en cada plan de feature antes de
  iniciar la implementación.
- Las pruebas automatizadas de seguridad (Principio VI) constituyen la verificación continua del
  cumplimiento en cada ciclo de desarrollo.
- Se realiza una revisión integral de la Constitución al inicio de cada ciclo de release mayor.

**Ámbito**: Esta Constitución aplica a todo el código, documentación y decisiones de diseño del
proyecto Gestor de Contraseñas Local, independientemente del contribuidor o la plataforma.

**Version**: 1.0.0 | **Ratified**: 2026-06-17 | **Last Amended**: 2026-06-17
