# Feature Specification: Gestor de Contraseñas Local y Offline

**Feature Branch**: `001-local-password-manager`

**Created**: 2026-06-17

**Status**: Draft

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Crear una Bóveda Nueva y Desbloquearla (Priority: P1)

Un usuario inicia la aplicación por primera vez y crea una nueva bóveda protegida con una
contraseña maestra de su elección. En sesiones posteriores, introduce la contraseña maestra para
desbloquear la bóveda y acceder a sus credenciales.

**Why this priority**: Sin la bóveda y el mecanismo de desbloqueo, ninguna otra funcionalidad es
posible. Es el bloque fundacional del que depende todo el sistema.

**Independent Test**: Se puede probar creando una bóveda vacía, cerrando la aplicación,
reabriendo y desbloqueando — esto ya entrega valor verificable: el usuario sabe que sus datos
están protegidos y accesibles solo con su contraseña.

**Acceptance Scenarios**:

1. **Given** la aplicación sin ninguna bóveda existente, **When** el usuario elige crear una
   nueva bóveda, proporciona una contraseña maestra y confirma la creación, **Then** se genera un
   archivo de bóveda cifrado en la ubicación elegida y la aplicación muestra la interfaz principal
   desbloqueada.

2. **Given** el usuario recibe una advertencia explícita de que la contraseña maestra no puede
   recuperarse, **When** el usuario confirma que comprende y acepta continuar, **Then** la bóveda
   se crea únicamente si el usuario ha confirmado la advertencia.

3. **Given** una bóveda existente, **When** el usuario introduce la contraseña maestra correcta,
   **Then** la bóveda se desbloquea y el usuario accede a sus entradas.

4. **Given** una bóveda existente, **When** el usuario introduce una contraseña maestra
   incorrecta, **Then** el acceso es denegado, no se expone ningún dato y se muestra un mensaje
   de error claro.

5. **Given** la bóveda desbloqueada, **When** el usuario elige bloquearla manualmente,
   **Then** la bóveda se bloquea inmediatamente y se requiere la contraseña maestra para volver
   a acceder.

---

### User Story 2 — Gestionar Entradas de Credenciales (Priority: P2)

Una vez que la bóveda está desbloqueada, el usuario puede agregar nuevas entradas de credenciales,
ver el detalle de una entrada existente, editar cualquier campo y eliminar entradas que ya no
necesita.

**Why this priority**: La gestión de entradas es el uso diario central de la aplicación.

**Independent Test**: Se puede probar con una bóveda vacía, agregando, editando y eliminando
entradas, luego bloqueando y reingresando para verificar la persistencia — entrega el MVP básico
de un gestor de contraseñas.

**Acceptance Scenarios**:

1. **Given** la bóveda desbloqueada, **When** el usuario selecciona agregar una nueva entrada y
   completa los campos (sitio/URL, usuario, contraseña, notas), **Then** la entrada queda
   guardada en la bóveda cifrada y aparece en la lista de entradas.

2. **Given** una entrada existente, **When** el usuario selecciona editarla y modifica uno o
   más campos, **Then** los cambios quedan guardados y se reflejan inmediatamente.

3. **Given** una entrada existente, **When** el usuario selecciona eliminarla y confirma la
   acción, **Then** la entrada se elimina de la bóveda de forma permanente.

4. **Given** el usuario intenta eliminar una entrada, **When** se muestra el diálogo de
   confirmación y el usuario cancela, **Then** la entrada no se elimina.

5. **Given** que se realizan cambios en las entradas, **When** el usuario bloquea la bóveda y
   la vuelve a desbloquear, **Then** todos los cambios persisten correctamente.

---

### User Story 3 — Buscar Entradas en Tiempo Real (Priority: P3)

Con la bóveda desbloqueada, el usuario escribe en el campo de búsqueda y la lista de entradas
se filtra instantáneamente para mostrar solo las que coinciden con el sitio/URL o el nombre
de usuario.

**Why this priority**: Con más de unas pocas decenas de entradas, la búsqueda es imprescindible
para una UX usable.

**Independent Test**: Se puede probar con una bóveda que contenga 20+ entradas y verificar que
el filtrado responde visualmente a cada pulsación de tecla.

**Acceptance Scenarios**:

1. **Given** una bóveda con varias entradas, **When** el usuario escribe texto en el campo de
   búsqueda, **Then** la lista muestra solo las entradas cuyo sitio/URL o usuario contenga el
   texto introducido, actualizándose con cada pulsación.

2. **Given** el campo de búsqueda con texto, **When** el usuario borra el texto, **Then** se
   muestran todas las entradas de la carpeta o vista activa.

3. **Given** una búsqueda sin resultados coincidentes, **When** el usuario ha introducido texto,
   **Then** la lista muestra un estado vacío con un mensaje informativo.

---

### User Story 4 — Generar Contraseñas Aleatorias Seguras (Priority: P4)

Al crear o editar una entrada, el usuario puede invocar el generador de contraseñas para obtener
una contraseña aleatoria con longitud y tipos de caracteres configurables, que se inserta
directamente en el campo contraseña.

**Why this priority**: El generador es una característica de valor que incentiva el uso de
contraseñas fuertes y únicas.

**Independent Test**: Se puede probar invocando el generador desde el formulario de nueva entrada
y verificando que el resultado cumple los parámetros configurados.

**Acceptance Scenarios**:

1. **Given** el formulario de creación o edición de entrada, **When** el usuario accede al
   generador de contraseñas, **Then** puede configurar la longitud (mínimo 8, máximo 128
   caracteres) y elegir qué conjuntos de caracteres incluir (mayúsculas, minúsculas, dígitos,
   símbolos).

2. **Given** la configuración seleccionada, **When** el usuario genera la contraseña, **Then**
   el resultado contiene únicamente caracteres de los conjuntos seleccionados y tiene la longitud
   especificada.

3. **Given** que el generador está activo, **When** el usuario hace clic en "usar esta
   contraseña", **Then** el campo contraseña de la entrada se rellena con el valor generado.

4. **Given** el generador, **When** el usuario solicita regenerar una contraseña, **Then** se
   produce un nuevo valor diferente sin perder la configuración.

---

### User Story 5 — Copiar Credenciales al Portapapeles con Borrado Automático (Priority: P5)

El usuario puede copiar el nombre de usuario o la contraseña de una entrada al portapapeles del
sistema con un solo clic. El contenido copiado se elimina automáticamente del portapapeles tras
un tiempo configurable.

**Why this priority**: Es la interacción más frecuente durante el uso diario y tiene implicaciones
directas de seguridad.

**Independent Test**: Se puede probar copiando una contraseña, pegándola en un editor de texto
para confirmar el valor, esperando el timeout y verificando que el portapapeles se ha limpiado.

**Acceptance Scenarios**:

1. **Given** una entrada desbloqueada, **When** el usuario activa la acción de copiar usuario o
   contraseña, **Then** el valor se copia al portapapeles del sistema y se muestra una
   confirmación visual transitoria.

2. **Given** el portapapeles contiene un valor copiado por la aplicación, **When** transcurre el
   tiempo de borrado configurado (default 20 segundos), **Then** el portapapeles se limpia
   automáticamente.

3. **Given** el portapapeles contiene un valor copiado, **When** el usuario bloquea la bóveda
   antes de que expire el timeout, **Then** el portapapeles se limpia inmediatamente al bloquear.

---

### User Story 6 — Organizar Entradas en Carpetas (Priority: P6)

El usuario puede crear carpetas, mover entradas a carpetas y navegar por las carpetas para ver
únicamente las entradas que contienen.

**Why this priority**: Las carpetas mejoran la organización para usuarios con muchas entradas,
pero no son bloqueantes para el MVP básico.

**Independent Test**: Se puede probar creando dos carpetas, distribuyendo entradas entre ellas y
verificando que al seleccionar una carpeta solo se muestran sus entradas.

**Acceptance Scenarios**:

1. **Given** la bóveda desbloqueada, **When** el usuario crea una carpeta nueva con un nombre,
   **Then** la carpeta aparece en la lista de carpetas.

2. **Given** una entrada existente, **When** el usuario la mueve a una carpeta, **Then** la
   entrada desaparece de la vista "Sin carpeta" y aparece bajo la carpeta destino.

3. **Given** el usuario selecciona una carpeta, **When** se muestra el contenido, **Then** solo
   se muestran las entradas asignadas a esa carpeta.

4. **Given** una carpeta con entradas, **When** el usuario intenta eliminar la carpeta,
   **Then** se advierte que las entradas pasarán a "Sin carpeta" y se requiere confirmación.

---

### User Story 7 — Auto-bloqueo por Inactividad (Priority: P7)

Si el usuario no interactúa con la aplicación durante un período configurable, la bóveda se
bloquea automáticamente, requiriendo la contraseña maestra para volver a acceder.

**Why this priority**: Protección fundamental ante acceso no autorizado en dispositivos
desatendidos. Requerimiento de seguridad explícito.

**Independent Test**: Se puede probar configurando un timeout corto (e.g., 10 segundos),
esperando sin interacción y verificando que la pantalla de desbloqueo se muestra.

**Acceptance Scenarios**:

1. **Given** la bóveda desbloqueada con el timeout de inactividad activo, **When** transcurre el
   período configurado sin ninguna interacción del usuario, **Then** la bóveda se bloquea
   automáticamente.

2. **Given** la bóveda bloqueada por inactividad, **When** el usuario introduce la contraseña
   maestra correcta, **Then** la bóveda se desbloquea y el usuario retorna al estado anterior.

3. **Given** el usuario interactúa con la aplicación, **When** se produce cualquier acción
   (pulsación de tecla, clic, scroll), **Then** el temporizador de inactividad se reinicia.

---

### Edge Cases

- ¿Qué ocurre si el archivo de bóveda está corrupto o modificado externamente? La aplicación lo
  detecta mediante el verificador de autenticidad del cifrado y muestra un error claro,
  rechazando la apertura sin exponer datos parciales.

- ¿Qué ocurre si el disco se queda sin espacio al guardar la bóveda? La operación de guardado
  falla de forma segura: no se escribe un archivo parcialmente cifrado; el estado en disco
  permanece en el estado válido anterior.

- ¿Qué ocurre si el portapapeles del sistema no está disponible? La aplicación muestra un
  mensaje de error; no se produce ninguna escritura silenciosa en archivos temporales.

- ¿Qué ocurre si el usuario configura el timeout de portapapeles a 0 (desactivado)? La
  aplicación lo permite pero muestra una advertencia de seguridad.

- ¿Qué ocurre si el generador de contraseñas solo tiene un tipo de carácter seleccionado?
  Genera la contraseña con ese único conjunto; la aplicación acepta la configuración sin error.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema DEBE permitir al usuario crear una nueva bóveda protegida por una
  contraseña maestra en una ubicación del sistema de archivos elegida por el usuario.

- **FR-002**: El sistema DEBE almacenar toda la información de la bóveda en un único archivo
  cifrado en el disco local.

- **FR-003**: El archivo de bóveda DEBE utilizar cifrado autenticado (AEAD) que garantice
  tanto la confidencialidad como la integridad de los datos.

- **FR-004**: La clave de cifrado DEBE derivarse de la contraseña maestra usando una función
  de derivación de clave (KDF) resistente a ataques de fuerza bruta, con un salt criptográfico
  único generado aleatoriamente en la creación de la bóveda.

- **FR-005**: El salt y los parámetros de la KDF DEBEN almacenarse en el archivo de bóveda
  (no son secretos) para permitir la derivación en futuros desbloqueos y la migración futura.

- **FR-006**: La clave derivada DEBE existir exclusivamente en memoria durante la sesión activa
  y NUNCA escribirse en disco en ninguna forma.

- **FR-007**: Ningún dato sensible descifrado (contraseñas, notas, usuarios) DEBE escribirse en
  disco fuera del archivo de bóveda cifrado.

- **FR-008**: El sistema DEBE permitir al usuario desbloquear la bóveda introduciendo la
  contraseña maestra correcta.

- **FR-009**: El sistema DEBE rechazar el acceso cuando la contraseña maestra introducida es
  incorrecta, sin exponer ningún dato parcial.

- **FR-010**: El sistema DEBE permitir agregar entradas de credenciales con los campos: sitio o
  URL, nombre de usuario, contraseña y notas.

- **FR-011**: El sistema DEBE permitir editar cualquier campo de una entrada existente.

- **FR-012**: El sistema DEBE permitir eliminar entradas, requiriendo confirmación explícita
  del usuario antes de la eliminación.

- **FR-013**: El sistema DEBE proporcionar búsqueda en tiempo real que filtre las entradas
  visibles por sitio/URL o nombre de usuario con cada pulsación de tecla.

- **FR-014**: El sistema DEBE incluir un generador de contraseñas aleatorias con longitud
  configurable (mínimo 8, máximo 128 caracteres) y selección de conjuntos de caracteres:
  mayúsculas, minúsculas, dígitos y símbolos.

- **FR-015**: El sistema DEBE permitir copiar el nombre de usuario o la contraseña de una
  entrada al portapapeles del sistema.

- **FR-016**: El contenido copiado por la aplicación al portapapeles DEBE eliminarse
  automáticamente tras un período configurable por el usuario, con un valor por defecto de
  20 segundos.

- **FR-017**: El sistema DEBE bloquear la bóveda automáticamente tras un período configurable
  de inactividad del usuario, con un valor por defecto de 5 minutos.

- **FR-018**: El sistema DEBE permitir al usuario organizar las entradas asignándolas a carpetas
  con nombre.

- **FR-019**: La aplicación DEBE funcionar completamente sin conexión de red y sin producir
  ninguna comunicación de red bajo ninguna circunstancia.

- **FR-020**: El sistema DEBE advertir explícitamente al usuario durante la creación de la
  bóveda que la contraseña maestra no puede recuperarse, y requerir confirmación antes de
  continuar.

- **FR-021**: El sistema NO DEBE proporcionar ningún mecanismo de recuperación, reinicio o
  derivación alternativa de la contraseña maestra.

- **FR-022**: El portapapeles DEBE limpiarse inmediatamente al bloquear la bóveda, sin esperar
  a que expire el timeout.

### Key Entities

- **Bóveda (Vault)**: Archivo cifrado en disco que contiene la totalidad de los datos del
  usuario. Atributos: blob cifrado, salt, parámetros de KDF, versión del formato.

- **Entrada (Entry)**: Registro individual de credencial dentro de la bóveda. Atributos:
  identificador único, sitio/URL, nombre de usuario, contraseña, notas, referencia a carpeta
  (opcional), fecha de creación, fecha de última modificación.

- **Carpeta (Folder)**: Contenedor de agrupación para entradas. Atributos: identificador único,
  nombre. Las carpetas son planas en v1 (sin anidamiento).

- **Sesión de Bóveda (VaultSession)**: Estado en memoria de la bóveda desbloqueada. Atributos:
  clave derivada (en memoria protegida), lista de entradas descifradas, marca de tiempo de
  última actividad. Nunca se persiste en disco.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un usuario nuevo puede crear una bóveda y registrar su primera entrada de
  credencial en menos de 2 minutos, sin formación previa.

- **SC-002**: El desbloqueo de la bóveda (desde la introducción de la contraseña hasta acceder
  a las entradas) se completa en menos de 1 segundo en un equipo de escritorio estándar.

- **SC-003**: Los resultados de búsqueda se actualizan visiblemente en menos de 100
  milisegundos tras cada pulsación de tecla, incluso con 500 entradas en la bóveda.

- **SC-004**: La copia de una credencial al portapapeles se ejecuta en menos de 50 milisegundos
  desde la acción del usuario.

- **SC-005**: El portapapeles se limpia automáticamente dentro del timeout configurado
  (por defecto 20 segundos), sin ninguna acción del usuario.

- **SC-006**: La bóveda se bloquea automáticamente dentro del timeout de inactividad configurado
  (por defecto 5 minutos), sin ninguna acción del usuario.

- **SC-007**: Los intentos de desbloqueo con contraseña incorrecta son siempre rechazados y
  nunca exponen datos parciales de la bóveda — verificable en el 100 % de los casos.

- **SC-008**: Ningún archivo en disco contiene datos sensibles en texto plano antes, durante ni
  después de cualquier sesión — verificable mediante inspección del sistema de archivos.

- **SC-009**: La aplicación produce cero tráfico de red durante cualquier operación —
  verificable mediante monitorización de red durante una sesión completa.

- **SC-010**: Una bóveda con 500 entradas puede buscarse, listarse y desplazarse sin retraso
  perceptible por parte del usuario.

---

## Assumptions

- **Un único usuario por bóveda**: Cada archivo de bóveda pertenece a un solo usuario. La
  gestión multi-usuario y el uso compartido están fuera del alcance de v1.

- **Interfaz gráfica de escritorio (GUI)**: La aplicación se ejecuta en sistemas operativos de
  escritorio (Linux, macOS, Windows) con interfaz gráfica. La capa visual está separada del
  núcleo lógico (cifrado, gestión de datos, generador de contraseñas); el núcleo no tiene
  dependencias de la UI. La elección del toolkit gráfico se define en el Plan. El soporte
  móvil está fuera del alcance de v1.

- **Una bóveda activa por sesión**: La aplicación gestiona una sola bóveda por sesión. El
  usuario puede tener múltiples archivos de bóveda en disco y abrir uno distinto en cada
  sesión, pero no puede tener varias bóvedas abiertas simultáneamente.

- **Sistema de archivos local**: El archivo de bóveda se almacena en el sistema de archivos
  local del dispositivo, en una ubicación elegida por el usuario.

- **Portapapeles del sistema operativo**: La aplicación usa la API de portapapeles del sistema
  operativo. El aislamiento del portapapeles entre aplicaciones es responsabilidad del SO.

- **Hardware estándar**: Los objetivos de rendimiento asumen un ordenador personal fabricado
  en los últimos 7 años.

- **Carpetas planas en v1**: Las carpetas no tienen anidamiento jerárquico en v1; todas las
  carpetas están al mismo nivel.

- **Solo español en v1**: La interfaz de usuario y todos los mensajes están en español. La
  internacionalización (soporte multi-idioma) queda fuera del alcance de v1.

- **Sin integración con navegador**: El autocompletado y los complementos de navegador están
  fuera del alcance de v1.

- **Sin recuperación de contraseña maestra**: Por diseño y requerimiento explícito; no se
  implementa ningún mecanismo de recuperación.

- **Sin sincronización en la nube**: El usuario es responsable de realizar copias de seguridad
  del archivo de bóveda.

- **Cambiar contraseña maestra: diferido a v2**: La funcionalidad de re-cifrado de la bóveda
  con una nueva contraseña maestra queda fuera del alcance de v1, junto con sincronización
  en la nube, compartir contraseñas, autocompletado de navegador, recuperación de contraseña
  maestra y app móvil.

---

## Clarifications

*Decisiones registradas el 2026-06-17 que reemplazan supuestos implícitos anteriores.*

| # | Tema | Decisión |
|---|------|----------|
| C-001 | Interfaz | Aplicación de escritorio con GUI. La capa visual está separada del núcleo lógico (cifrado, datos, generador). La elección del toolkit gráfico se define en el Plan, no en la especificación. |
| C-002 | Modelo de bóveda | Una bóveda por archivo; la aplicación gestiona una sola bóveda por sesión. El usuario puede tener múltiples archivos en disco pero no abre varios simultáneamente. |
| C-003 | Borrado de carpeta | Al eliminar una carpeta se muestra un diálogo de confirmación y sus entradas se mueven automáticamente a "Sin carpeta". Las entradas nunca se eliminan junto con la carpeta. |
| C-004 | Timeout portapapeles | Valor por defecto: **20 segundos** (actualizado desde 30 s). Configurable por el usuario. |
| C-005 | Auto-bloqueo | Valor por defecto: **5 minutos**. Configurable. Sin cambio respecto al valor original. |
| C-006 | Idioma | Solo **español** en v1. La internacionalización queda fuera del alcance de v1. |
| C-007 | Cambiar contraseña maestra | **Diferido a v2.** Se añade a la lista de funcionalidades fuera de alcance de v1. |
