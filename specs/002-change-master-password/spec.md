# Feature Specification: Cambiar Contraseña Maestra (Rotación de la Maestra)

**Feature Branch**: `002-change-master-password`

**Created**: 2026-06-29

**Status**: Draft

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Rotación Exitosa de la Contraseña Maestra (Priority: P1)

Con la bóveda ya desbloqueada, el usuario accede al flujo de cambio de maestra, introduce su
contraseña maestra actual (verificada contra la bóveda), introduce una maestra nueva dos veces
(confirmación coincidente), y el sistema re-cifra toda la bóveda con una llave derivada del salt
nuevo y persiste el resultado de forma atómica. Al terminar, solo la contraseña nueva abre la
bóveda; la antigua deja de servir.

**Why this priority**: Es el caso de uso principal de la feature. Sin esta historia completa y
correcta no existe la funcionalidad. Todas las demás historias son condiciones de corrección o
variantes de error de esta misma operación central.

**Independent Test**: Se puede probar creando una bóveda con entradas, ejecutando la rotación con
éxito, cerrando la aplicación y reabriendo: si solo la contraseña nueva desbloquea la bóveda y la
antigua produce un error de autenticación, la historia está verificada.

**Acceptance Scenarios**:

1. **Given** la bóveda desbloqueada con entradas y carpetas, **When** el usuario introduce la
   maestra actual correcta y una nueva maestra con confirmación coincidente, **Then** el sistema
   genera un salt nuevo, deriva una llave nueva, re-cifra toda la bóveda, reemplaza el archivo de
   forma atómica y muestra confirmación de éxito.

2. **Given** la bóveda re-cifrada exitosamente, **When** el usuario cierra la aplicación y vuelve
   a abrirla, **Then** la contraseña nueva desbloquea la bóveda con todas las entradas intactas y
   la contraseña anterior produce un error de autenticación inmediato.

3. **Given** la bóveda re-cifrada exitosamente, **When** se inspecciona el archivo de bóveda,
   **Then** el salt registrado en los metadatos es diferente al salt que existía antes de la
   rotación, y el contenido no es legible sin la contraseña nueva.

4. **Given** la bóveda re-cifrada exitosamente, **When** un proceso externo intenta descifrar la
   bóveda usando la contraseña anterior, **Then** la operación falla con un error de autenticación
   sin exponer ningún dato parcial.

---

### User Story 2 — Re-autenticación Explícita con la Maestra Actual (Priority: P1)

Aunque la sesión esté abierta y la bóveda desbloqueada, el flujo de cambio de maestra exige que
el usuario introduzca su contraseña maestra actual antes de proceder. Este paso no se puede omitir
ni sustituir por el estado de sesión existente.

**Why this priority**: Sin esta verificación, cualquier persona que encuentre la pantalla
desbloqueada podría cambiar la contraseña maestra sin conocerla. Es una re-autenticación
deliberada que protege contra acceso físico no autorizado.

**Independent Test**: Se puede probar intentando iniciar el flujo de cambio con la bóveda
desbloqueada e introduciendo una maestra actual incorrecta: el sistema debe rechazarlo sin
modificar el archivo, byte a byte idéntico al estado previo.

**Acceptance Scenarios**:

1. **Given** la bóveda desbloqueada, **When** el usuario accede al flujo de cambio de maestra,
   **Then** el sistema solicita la contraseña maestra actual antes de presentar los campos de la
   contraseña nueva.

2. **Given** el flujo de cambio de maestra activo, **When** el usuario introduce una contraseña
   maestra actual incorrecta, **Then** el sistema muestra un error claro, no inicia ninguna
   operación de re-cifrado y el archivo de bóveda permanece byte a byte idéntico al estado previo.

3. **Given** el flujo de cambio de maestra activo, **When** el usuario cancela antes de confirmar
   la nueva contraseña, **Then** no se produce ninguna modificación en el archivo de bóveda.

---

### User Story 3 — Resistencia a Interrupciones y Consistencia de la Bóveda (Priority: P1)

Si el proceso de re-cifrado se interrumpe en cualquier punto (corte de luz, cierre forzado,
fallo del sistema) la bóveda nunca queda en un estado corrupto o parcialmente escrito. Al
reabrir, la bóveda es siempre consistente: o la versión anterior (si no se alcanzó el commit)
o la nueva (si el commit se completó). No quedan archivos temporales residuales.

**Why this priority**: La posible corrupción de la bóveda es el riesgo más grave de la feature:
el usuario podría perder acceso permanente a todas sus credenciales. Este requisito es
innegociable según la constitución (Principio I: Seguridad por Diseño).

**Independent Test**: Se puede probar simulando una interrupción (eliminando el proceso) durante
el re-cifrado y verificando que el archivo de bóveda sigue siendo descifrable con la contraseña
anterior, y que no quedan archivos temporales en el directorio de la bóveda.

**Acceptance Scenarios**:

1. **Given** el proceso de re-cifrado en curso antes del reemplazo atómico, **When** se
   interrumpe el proceso abruptamente, **Then** el archivo de bóveda original permanece intacto y
   sigue siendo descifrable con la contraseña maestra anterior.

2. **Given** el proceso de re-cifrado completa el reemplazo atómico (punto de commit), **When**
   se interrumpe el proceso inmediatamente después, **Then** el archivo de bóveda contiene la
   versión nueva completamente escrita, descifrable únicamente con la nueva contraseña maestra.

3. **Given** cualquier escenario de interrupción (antes o después del commit), **When** se
   examina el directorio de la bóveda, **Then** no existe ningún archivo temporal residual
   relacionado con la operación de rotación.

4. **Given** una interrupción antes del commit, **When** el usuario vuelve a abrir la aplicación,
   **Then** la bóveda está en el estado previo a la rotación, completamente funcional, sin rastro
   de la operación incompleta.

5. **Given** el proceso de rotación activo con el temporizador de auto-bloqueo configurado,
   **When** la derivación KDF o el re-cifrado tarda más que el intervalo de auto-bloqueo,
   **Then** el temporizador está suspendido y no se dispara durante la operación; al finalizar
   (con éxito, fallo o cancelación), el temporizador se reanuda desde cero.

---

### User Story 4 — Validación de la Nueva Contraseña y Mensajes de Error (Priority: P2)

El flujo de cambio de maestra valida que la nueva contraseña y su confirmación coincidan antes
de iniciar cualquier operación de re-cifrado. Los errores de validación se comunican de forma
clara sin bloquear al usuario fuera de su bóveda.

**Why this priority**: Protege al usuario de quedar bloqueado fuera de su propia bóveda por una
errata tipográfica en la nueva contraseña. Un error de tecleo no debe tener consecuencias
irreversibles.

**Independent Test**: Se puede probar introduciendo contraseñas nueva y confirmación que no
coincidan: el sistema debe rechazarlo antes de iniciar cualquier operación de re-cifrado.

**Acceptance Scenarios**:

1. **Given** el flujo de cambio activo con la maestra actual verificada, **When** el usuario
   introduce una nueva contraseña y una confirmación que no coincide, **Then** el sistema muestra
   un mensaje de error específico y no inicia la operación de re-cifrado.

2. **Given** el flujo de cambio activo, **When** el usuario introduce una nueva contraseña
   vacía, **Then** el sistema rechaza la entrada con un mensaje claro antes de iniciar
   cualquier operación.

3. **Given** un error de validación en la nueva contraseña, **When** el usuario corrige los
   campos y vuelve a intentar, **Then** el flujo continúa normalmente sin necesidad de
   re-introducir la contraseña actual.

4. **Given** el flujo de cambio activo con la maestra actual verificada, **When** el usuario
   introduce una nueva contraseña idéntica a la contraseña actual, **Then** el sistema rechaza
   la entrada con un mensaje específico indicando que la nueva contraseña no puede ser igual a
   la actual, sin iniciar ninguna operación de re-cifrado.

5. **Given** el flujo de cambio activo, **When** el usuario introduce una nueva contraseña con
   menos de 12 caracteres, **Then** el sistema rechaza la entrada con un mensaje claro indicando
   la longitud mínima requerida (12 caracteres), sin iniciar ninguna operación de re-cifrado.

6. **Given** el flujo de cambio activo, **When** el usuario escribe la nueva contraseña,
   **Then** el sistema muestra el indicador de fortaleza (reutilizado del ciclo 001) como aviso
   informativo; el indicador no bloquea el envío del formulario siempre que se cumplan la
   longitud mínima (FR-019) y la no-identidad (FR-018).

---

### User Story 5 — Higiene de Memoria y Ausencia de Restos en Disco (Priority: P1)

Al completar la rotación (con éxito o con fallo), el sistema elimina de memoria la contraseña
maestra actual, la contraseña maestra nueva y ambas claves criptográficas derivadas. No quedan
en disco copias cifradas bajo la contraseña anterior ni copias descifradas de la bóveda.

**Why this priority**: Es un requisito de seguridad no negociable derivado del Principio I y III
de la constitución. Un usuario puede rotar precisamente porque sospecha que su contraseña anterior
fue comprometida; dejar una copia cifrada bajo esa contraseña anularía el propósito de la rotación.

**Independent Test**: Se puede verificar que tras la rotación exitosa no existan archivos con la
extensión de bóveda en el directorio distintos al archivo final, y que intentar descifrar el
archivo final con la contraseña anterior falle.

**Acceptance Scenarios**:

1. **Given** la rotación completada exitosamente, **When** se examina el directorio de la bóveda,
   **Then** no existe ningún archivo cifrado bajo la contraseña anterior ni ningún archivo
   temporal; solo el archivo de bóveda con la nueva cifrado.

2. **Given** la rotación fallida o cancelada, **When** se examina el directorio de la bóveda,
   **Then** el archivo original bajo la contraseña anterior está intacto y no existe ningún
   residuo de la operación incompleta.

3. **Given** la rotación completada, **When** se intenta abrir el archivo de bóveda con la
   contraseña anterior mediante cualquier medio, **Then** la operación falla con un error de
   autenticación.

---

### Edge Cases

- ¿Qué ocurre si el sistema de archivos no tiene espacio suficiente para escribir el archivo
  temporal de la bóveda re-cifrada?
- ¿Qué ocurre si la bóveda está vacía (sin entradas) cuando se solicita la rotación?
- ¿Qué ocurre si el archivo de bóveda es eliminado externamente durante el proceso de re-cifrado?
- La nueva contraseña idéntica a la actual se rechaza con un mensaje específico antes de iniciar cualquier operación; el archivo de bóveda no se toca (FR-018).
- ¿Qué sucede si la bóveda contiene un número muy elevado de entradas (≥ 1.000) y el re-cifrado
  tarda varios segundos?
- ¿Qué ocurre si se pierden los permisos de escritura sobre el archivo de bóveda durante la
  operación?
- Si el temporizador de auto-bloqueo tiene un intervalo muy corto y la rotación de una bóveda
  grande supera ese intervalo, el temporizador está suspendido durante la operación y no provoca
  un bloqueo a mitad de proceso (FR-021).

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema DEBE exigir que la bóveda esté desbloqueada para iniciar el flujo de
  cambio de contraseña maestra. El punto de entrada es un ítem de menú o botón
  "Cambiar contraseña maestra…" accesible exclusivamente desde la vista principal con la bóveda
  desbloqueada; es inaccesible en la vista de arranque, en la pantalla de desbloqueo y con la
  bóveda bloqueada. La activación de ese ítem abre un diálogo modal propio que contiene todo el
  flujo de cambio.

- **FR-002**: El sistema DEBE solicitar la contraseña maestra actual como paso explícito de
  re-autenticación, incluso cuando la sesión esté activa y la bóveda desbloqueada. Este paso no
  puede omitirse ni derivarse del estado de sesión existente.

- **FR-003**: El sistema DEBE verificar la contraseña maestra actual contra el archivo de bóveda
  antes de continuar con cualquier otra acción del flujo de cambio.

- **FR-004**: Si la contraseña maestra actual introducida es incorrecta, el sistema DEBE rechazar
  la operación con un mensaje de error claro y dejar el archivo de bóveda byte a byte idéntico
  al estado previo a la solicitud.

- **FR-005**: El sistema DEBE solicitar la nueva contraseña maestra mediante dos campos
  independientes (nueva contraseña y confirmación) y validar que ambos coincidan exactamente antes
  de iniciar cualquier operación de re-cifrado.

- **FR-018**: El sistema DEBE rechazar la nueva contraseña maestra si es idéntica a la
  contraseña maestra actual. El rechazo ocurre en la validación del formulario, antes de
  cualquier operación de re-cifrado, y va acompañado de un mensaje específico.

- **FR-019**: El sistema DEBE exigir que la nueva contraseña maestra tenga una longitud mínima
  de 12 caracteres. El rechazo por longitud ocurre en la validación del formulario, antes de
  cualquier operación de re-cifrado, y va acompañado de un mensaje que indica la longitud mínima.

- **FR-020**: El sistema DEBE mostrar un indicador de fortaleza de la nueva contraseña
  (reutilizado del ciclo 001 si existe) mientras el usuario la escribe. El indicador es
  puramente informativo: no bloquea el envío si se cumplen FR-018 y FR-019. No constituye un
  requisito de fortaleza mínima adicional al de longitud.

- **FR-006**: El sistema DEBE generar un salt criptográficamente aleatorio nuevo para cada
  rotación de contraseña maestra. Queda estrictamente prohibida la reutilización del salt anterior.

- **FR-007**: El sistema DEBE re-cifrar la bóveda completa —todas las entradas y carpetas— bajo
  la clave derivada de la nueva contraseña maestra y el salt nuevo. El contenido lógico de cada
  entrada no se modifica; solo el cifrado que lo protege.

- **FR-008**: El sistema DEBE usar un nonce nuevo para la operación de re-cifrado (la unicidad del
  nonce respecto a la clave nueva es obligatoria).

- **FR-009**: El sistema DEBE autenticar los nuevos metadatos del archivo (salt nuevo, parámetros
  KDF, versión) como datos adicionales (AAD) en la operación de cifrado autenticado, de modo que
  cualquier modificación posterior de esos metadatos cause un fallo de descifrado.

- **FR-010**: El sistema DEBE persistir la bóveda re-cifrada de forma atómica: escribir el
  resultado completo en un archivo temporal y solo entonces reemplazar el archivo original. El
  punto de commit es el reemplazo del archivo.

- **FR-011**: El sistema DEBE garantizar que el archivo de bóveda original permanezca intacto y
  descifrable con la contraseña anterior en cualquier instante anterior al commit atómico.

- **FR-012**: El sistema DEBE eliminar el archivo temporal inmediatamente tras el commit exitoso o
  ante cualquier fallo durante el proceso. No deben quedar archivos temporales residuales.

- **FR-013**: El sistema DEBE limpiar de memoria la contraseña maestra actual, la contraseña
  maestra nueva y ambas claves criptográficas derivadas (la antigua y la nueva) en cuanto dejen
  de ser necesarias, tanto en el camino de éxito como en el de fallo.

- **FR-014**: Tras la rotación exitosa, el archivo de bóveda en disco DEBE ser descifrable
  exclusivamente con la nueva contraseña maestra. No debe quedar en disco ninguna copia cifrada
  bajo la contraseña anterior ni ninguna copia en texto claro.

- **FR-015**: El sistema DEBE mostrar retroalimentación visible al usuario cuando la operación
  de re-cifrado tarda más de lo esperado (aplica especialmente a bóvedas con muchas entradas).

- **FR-016**: Tras una rotación exitosa, la bóveda DEBE permanecer desbloqueada con la llave
  nueva activa en memoria. La sesión continúa sin requerir que el usuario reintroduzca la nueva
  contraseña. La contraseña maestra actual (antigua), la contraseña maestra nueva en claro y la
  clave criptográfica derivada de la contraseña anterior DEBEN limpiarse de memoria
  inmediatamente tras el commit atómico, antes de devolver el control al usuario.

- **FR-017**: La rotación DEBE preservar los parámetros de coste de la KDF (factor de memoria,
  factor de CPU, paralelismo) tal como están registrados en los metadatos de la bóveda actual.
  La rotación no modifica los parámetros KDF. La atualización de parámetros KDF queda fuera del
  alcance de este ciclo (clasificado como *Could* para un ciclo futuro independiente); la
  protección anti-degradación vía AAD (NFR-003) cubre el ataque de downgrade en la bóveda
  resultante.

- **FR-021**: El sistema DEBE suspender el temporizador de auto-bloqueo por inactividad durante
  toda la operación de rotación (desde que el usuario confirma la nueva contraseña hasta que la
  operación termina con éxito, con fallo o con cancelación). Al terminar, el temporizador DEBE
  reanudarse desde cero. Si la operación termina con éxito, la bóveda queda desbloqueada con la
  llave nueva (FR-016) y el temporizador reinicia. Si falla o se cancela, la bóveda permanece
  desbloqueada con la llave anterior y el temporizador reinicia. En ninguna circunstancia el
  auto-bloqueo interrumpe la operación de re-cifrado.

### Non-Functional Requirements — Seguridad *(NON-NEGOTIABLE, según constitución)*

- **NFR-001 — Salt único por rotación**: Cada operación de cambio de contraseña maestra DEBE
  generar un salt criptográficamente aleatorio nuevo de mínimo 16 bytes. El salt anterior NUNCA
  se reutiliza. El salt nuevo se almacena en los metadatos de la nueva bóveda como dato no secreto.

  *Criterio de aceptación*: El salt registrado en los metadatos tras la rotación es diferente al
  salt registrado antes de la rotación. Dos rotaciones consecutivas producen dos salts diferentes.

- **NFR-002 — Re-cifrado atómico**: Una interrupción en cualquier punto del proceso de re-cifrado
  DEBE dejar la bóveda en un estado consistente. Antes del commit (reemplazo del archivo), la
  bóveda original permanece intacta y funcional bajo la contraseña anterior. Después del commit,
  la bóveda nueva está completa y es funcional bajo la contraseña nueva. En ningún instante puede
  existir un archivo a medio escribir que sea confundido con la bóveda válida.

  *Criterio de aceptación*: Simulando una interrupción abrupta antes del reemplazo del archivo,
  la bóveda es descifrable con la contraseña anterior. Simulando una interrupción después del
  reemplazo, la bóveda es descifrable con la nueva contraseña. En ambos casos, no existen archivos
  temporales residuales.

- **NFR-003 — Anti-degradación vía AAD**: Los metadatos del nuevo archivo de bóveda (salt, versión,
  parámetros KDF) DEBEN autenticarse como datos adicionales (AAD) en la operación AEAD, heredando
  la protección anti-degradación implementada en el ciclo 001. Modificar cualquiera de estos
  metadatos —incluida una reducción del coste KDF— DEBE provocar un fallo de descifrado.

  *Criterio de aceptación*: Modificando manualmente los parámetros KDF, el número de versión
  o el salt en los metadatos del archivo re-cifrado, el intento de descifrado falla con un error
  de autenticación.

- **NFR-004 — Higiene de memoria**: La ventana de tiempo durante la cual la contraseña maestra
  actual, la contraseña maestra nueva y las claves derivadas (antigua y nueva) coexisten en
  memoria DEBE minimizarse. El sistema DEBE limpiar (sobreescribir) estos valores en cuanto dejen
  de ser necesarios, tanto en el camino de éxito como en cualquier camino de error o cancelación.

  *Criterio de aceptación*: Tras la rotación (exitosa, fallida o cancelada), no es posible
  recuperar la contraseña anterior ni la nueva a través de una inspección del estado en memoria de
  la aplicación. Los objetos de contraseña y de clave se limpian explícitamente al terminar su
  uso.

- **NFR-005 — Ausencia de restos en disco**: Al completar la rotación (con éxito o con fallo), no
  debe quedar en disco ninguna copia descifrada de la bóveda ni ninguna copia cifrada bajo la
  contraseña anterior. El único archivo admitido es la bóveda final bajo la contraseña nueva (en
  caso de éxito) o la bóveda original sin modificar (en caso de fallo/cancelación).

  *Criterio de aceptación*: Tras la rotación exitosa, no existe ningún archivo en el directorio
  de la bóveda que sea descifrable con la contraseña anterior. Tras un fallo o cancelación, no
  existe ningún residuo temporal y el archivo original permanece intacto.

- **NFR-006 — Operación 100 % offline**: La feature DEBE funcionar exclusivamente de forma local.
  No se realiza ninguna comunicación de red, sincronización, telemetría ni llamada a servicio
  externo durante ni después de la rotación (constitución, Principio II).

  *Criterio de aceptación*: La rotación se completa con éxito con el dispositivo sin conexión
  de red. No se genera ningún tráfico de red observable durante la operación.

- **NFR-007 — Errores seguros**: Ante cualquier error (contraseña actual incorrecta, fallo de
  escritura, etc.), los mensajes NO deben filtrar el estado interno de la bóveda, el contenido de
  las claves ni datos sensibles. En el re-auth de SESIÓN ABIERTA —donde la bóveda ya está
  descifrada y validada en memoria, y su existencia/validez ya es conocida por quien tiene acceso
  físico— SÍ se permite un mensaje claro de "contraseña actual incorrecta" (mejora la usabilidad
  sin coste de seguridad). La indistinguibilidad entre "contraseña incorrecta" y "archivo dañado"
  aplica a la pantalla de DESBLOQUEO (dominio del ciclo 001), no a este flujo.

  *Criterio de aceptación*: Ante contraseña actual incorrecta durante la rotación, el archivo de
  bóveda permanece byte a byte intacto y la sesión sigue desbloqueada con la llave original.

### Non-Functional Requirements — Rendimiento

- **NFR-008 — Tiempo de re-cifrado**: El re-cifrado de una bóveda de hasta 1.000 entradas DEBE
  completarse en un tiempo aceptable desde la perspectiva del usuario (incluyendo la derivación
  KDF deliberadamente costosa). El sistema DEBE proporcionar retroalimentación visual si la
  operación supera los 2 segundos.

  *Criterio de aceptación*: Para una bóveda de 1.000 entradas, la rotación se completa (o muestra
  progreso visible) en no más de 10 segundos en hardware de referencia.

- **NFR-009 — No bloqueo de la UI**: La operación de re-cifrado y la derivación KDF NO DEBEN
  bloquear la interfaz de usuario. DEBEN ejecutarse en un hilo o proceso separado, permitiendo
  al menos mostrar un indicador de progreso.

  *Criterio de aceptación*: Durante la operación de rotación, la interfaz de usuario no se
  congela; es posible mostrar un indicador de progreso o cancelación.

### Key Entities *(datos afectados)*

- **Bóveda (Vault)**: La entidad central afectada por la rotación. Sus metadatos de cifrado
  (salt, parámetros KDF, versión, AAD) cambian completamente. El contenido lógico de entradas y
  carpetas no varía; solo cambia el cifrado que los protege.

- **Metadatos de Bóveda**: Contienen el salt (nuevo tras cada rotación), los parámetros de la
  KDF (algoritmo, coste de memoria, coste CPU) y la versión del formato. Son datos no secretos
  almacenados junto al archivo cifrado y autenticados como AAD.

- **Contraseña Maestra**: Entidad de datos volátil, nunca persistida. Tiene ciclo de vida
  estrictamente acotado: existe en memoria solo durante el tiempo necesario para la verificación
  (contraseña actual) y la derivación de la clave nueva (contraseña nueva), y se limpia
  inmediatamente después.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Tras una rotación exitosa, cerrar y reabrir la aplicación, solo la contraseña nueva
  desbloquea la bóveda; la contraseña anterior produce un error de autenticación en el 100 % de
  los intentos.

- **SC-002**: Simulando una interrupción abrupta durante el re-cifrado, la bóveda no queda nunca
  en un estado corrupto o parcialmente escrito; siempre es posible desbloquearla con alguna de
  las dos contraseñas según el punto de interrupción.

- **SC-003**: Introduciendo una contraseña maestra actual incorrecta, el sistema rechaza la
  operación y el archivo de bóveda permanece byte a byte idéntico al estado previo en el 100 %
  de los casos.

- **SC-004**: Modificando los metadatos de cifrado del archivo re-cifrado (salt, parámetros KDF,
  versión), el intento de descifrado falla con un error de autenticación en el 100 % de los casos.

- **SC-005**: Tras la rotación (exitosa, fallida o cancelada), no existe en disco ningún archivo
  temporal residual ni ninguna copia de la bóveda cifrada bajo la contraseña anterior.

- **SC-006**: El flujo de cambio de maestra se completa desde la pantalla de la bóveda
  desbloqueada en no más de 5 pasos de interacción del usuario (introducir maestra actual,
  introducir maestra nueva, confirmar maestra nueva, confirmar la acción, ver resultado).

- **SC-007**: La re-cifrado de una bóveda de hasta 1.000 entradas proporciona retroalimentación
  visual continua y no congela la interfaz de usuario.

---

## Assumptions

- La bóveda usa el esquema criptográfico definido en el ciclo 001: Argon2id para derivación de
  clave y AES-256-GCM para cifrado autenticado, con AAD anti-degradación. No se introduce ninguna
  primitiva criptográfica nueva.

- La escritura atómica (archivo temporal + reemplazo) ya está implementada en el núcleo del
  ciclo 001 y esta feature la reutiliza sin modificación de primitivas.

- La feature opera exclusivamente sobre una bóveda única (no existe gestión multi-bóveda en este
  ciclo). El archivo de bóveda ya existe y está desbloqueado cuando se inicia la rotación.

- Los parámetros KDF (coste de memoria, coste CPU, longitud del salt) se preservan tal como están
  en la bóveda actual; la rotación no los modifica (FR-017). La actualización de parámetros KDF
  es un *Could* de ciclo futuro independiente.

- La re-autenticación con la contraseña maestra actual es obligatoria aunque la sesión esté
  abierta (decisión de seguridad: re-pedir siempre, recomendado como "sí" en la descripción
  original del IDEA).

- La ubicación del punto de entrada en la UI es un botón o ítem de menú "Cambiar contraseña
  maestra…" en la vista principal de la bóveda desbloqueada, que abre un diálogo modal propio
  (FR-001). No existe ningún punto de entrada en el flujo de arranque ni en la pantalla de
  desbloqueo.

- El sistema de archivos subyacente soporta la operación de reemplazo atómico a nivel de
  directorio (rename/replace semántico). En sistemas donde esto no aplique, el comportamiento
  de atomicidad debe documentarse como limitación.

- La cobertura de tests sobre el módulo de servicio de rotación DEBE ser ≥ 95 % (constitución,
  Principio VI), con tests específicos para: salt nuevo, atomicidad, AAD, higiene de memoria
  e invalidación de la contraseña anterior.

---

## Clarifications

### Session 2026-06-29

- Q: ¿Se rechaza la nueva maestra cuando es idéntica a la actual? ¿Se exige una fortaleza mínima
  medible? → A: Sí se rechaza la nueva maestra idéntica a la actual (única regla dura junto con
  la longitud); longitud mínima de 12 caracteres como único umbral duro; el indicador de
  fortaleza de 001 actúa como aviso informativo, no como muro de bloqueo. Afecta a: US4
  escenarios 4–6 · FR-018 · FR-019 · FR-020.
- Q: Tras una rotación exitosa, ¿la bóveda queda desbloqueada con la llave nueva en memoria o
  se fuerza re-desbloqueo? → A: La bóveda permanece desbloqueada con la llave nueva en memoria;
  la llave antigua, la contraseña actual y la contraseña nueva en claro se limpian de memoria
  inmediatamente tras el commit atómico. No se requiere re-desbloqueo (la nueva contraseña ya
  fue autenticada dos veces al confirmarla). Afecta a: FR-016.
- Q: ¿La rotación conserva los parámetros KDF actuales o permite subirlos? → A: Conserva siempre
  los parámetros KDF existentes; la actualización queda como *Could* de ciclo futuro. La AAD
  (NFR-003) ya cubre el ataque de downgrade en la bóveda resultante. Afecta a: FR-017 ·
  Assumptions.
- Q: ¿Dónde vive el punto de entrada del cambio de maestra en la UI? → A: Botón o ítem de menú
  "Cambiar contraseña maestra…" en la vista principal de la bóveda desbloqueada; al activarlo
  se abre un diálogo modal propio. Ningún punto de entrada en el flujo de arranque ni en la
  pantalla de desbloqueo. Afecta a: FR-001 · Assumptions.
- Q: Si el auto-bloqueo por inactividad de 001 salta durante la rotación, ¿se suspende el
  temporizador o se aborta limpiamente? → A: El temporizador se suspende durante toda la
  operación de rotación y se reanuda desde cero al terminar (con éxito, fallo o cancelación).
  El auto-bloqueo nunca interrumpe el re-cifrado; el aborto antes del commit deja la bóveda
  original intacta (coherente con NFR-002). Afecta a: FR-021 · US3 escenario 5 · Edge Cases.

- Q: ¿NFR-007 exige indistinguibilidad de errores también en el re-auth de sesión abierta? → A:
  No; en sesión abierta la bóveda ya está validada en memoria, así que se permite un mensaje
  claro de "contraseña actual incorrecta". La indistinguibilidad se mantiene solo en la pantalla
  de desbloqueo (ciclo 001). Afecta a: NFR-007 · research.md · contracts/vault-service-interface.md.
