# IDEA — Gestor de Contraseñas Local y Offline

> **Documento primigenio (semilla).** Captura *qué* queremos construir y *por qué*, sin decidir todavía la tecnología. Es la fuente que alimentará el comando `/speckit.specify` de Spec Kit (ver el *Manual*). Las decisiones de stack se toman más adelante, en la fase de Plan.

---

## 1. Resumen en una frase

Una aplicación de escritorio **local y offline** que guarda tus contraseñas en un **único archivo cifrado**, protegido por una **contraseña maestra**, y permite crear, editar, eliminar, buscar y organizar entradas por carpetas, además de generar contraseñas seguras y copiarlas al portapapeles.

## 2. Problema y motivación (el *por qué*)

Mucha gente reutiliza contraseñas o las guarda en notas y hojas de cálculo sin cifrar. Los gestores en la nube implican confiar datos sensibles a terceros y requieren conexión. Queremos una alternativa **simple, privada y sin servidores**: los datos nunca salen del equipo del usuario y la seguridad es el principio rector de todo el diseño.

## 3. Objetivo principal

Permitir que una persona almacene y recupere sus credenciales de forma segura, **sin conexión a internet y sin servicios externos**, con una experiencia rápida para las tareas diarias (buscar, copiar, agregar).

## 4. Usuarios objetivo

- **Usuario individual** preocupado por su privacidad, con un solo equipo personal.
- Perfil **no técnico**: la interfaz debe ser clara; la seguridad no debe exigir conocimientos avanzados.
- (Posible más adelante) usuario que mueve manualmente su archivo cifrado entre equipos mediante USB o su propia nube.

## 5. Alcance funcional (el *qué*), priorizado

Se usa **MoSCoW**: *Must* (imprescindible v1), *Should* (deseable), *Could* (futuro).

### Must — versión 1
- **Bóveda cifrada:** todos los datos se guardan en un único archivo cifrado en disco.
- **Contraseña maestra:** se exige al abrir la aplicación; es la única llave para descifrar la bóveda.
- **Gestión de entradas (CRUD):** agregar, editar, eliminar entradas con los campos **sitio / URL**, **usuario**, **contraseña** y **notas**.
- **Búsqueda:** filtrar entradas por sitio o usuario en tiempo real.
- **Generador de contraseñas seguras:** longitud configurable y selección de tipos de caracteres (mayúsculas, minúsculas, números, símbolos).
- **Copiar al portapapeles:** copiar usuario o contraseña con un clic.
- **Organización por carpetas:** agrupar entradas en carpetas/categorías.

### Should
- **Auto-bloqueo** tras un periodo de inactividad configurable.
- **Borrado automático del portapapeles** unos segundos después de copiar.
- **Indicador de fortaleza** de cada contraseña.
- **Mostrar/ocultar** la contraseña en pantalla.
- **Crear bóveda nueva** y **cambiar la contraseña maestra**.

### Could (fuera de la v1, anotado para el futuro)
- Exportar/importar (en formato cifrado o texto bajo advertencia).
- Detección de contraseñas duplicadas o débiles.
- Campos personalizados y adjuntos.
- Copia de seguridad automática del archivo de bóveda.

## 6. Requisitos no funcionales — **la seguridad es prioritaria**

> Estos requisitos tienen el mismo peso (o mayor) que los funcionales. Cualquier conflicto se resuelve a favor de la seguridad.

- **Cifrado en reposo:** la bóveda completa debe almacenarse cifrada con un esquema de **cifrado autenticado** (que detecte manipulación del archivo).
- **Derivación de la llave:** la llave de cifrado se deriva de la contraseña maestra mediante una **función de derivación resistente a fuerza bruta** (con factor de costo configurable y *salt* único por bóveda).
- **Cero conocimiento / local:** la contraseña maestra y los datos descifrados **nunca se escriben en disco sin cifrar** ni se envían a ninguna red.
- **Sin telemetría ni conexiones externas:** la app debe funcionar completamente **offline**.
- **Datos en memoria:** minimizar el tiempo que los secretos permanecen en memoria; limpiar cuando sea posible al bloquear o cerrar.
- **Errores seguros:** ante contraseña maestra incorrecta o archivo corrupto, fallar sin filtrar información.
- **Multiplataforma deseable:** idealmente Windows, macOS y Linux (a confirmar en el Plan).
- **Rendimiento:** abrir, buscar y copiar deben sentirse instantáneos para bóvedas de hasta ~1.000 entradas.
- **Usabilidad:** flujo de uso diario en pocos clics; mensajes claros.

## 7. Historias de usuario

1. **Como** usuario nuevo, **quiero** crear una bóveda con una contraseña maestra **para** empezar a guardar credenciales de forma cifrada.
2. **Como** usuario, **quiero** desbloquear la aplicación con mi contraseña maestra **para** acceder a mis entradas.
3. **Como** usuario, **quiero** agregar una entrada con sitio, usuario y contraseña **para** no tener que recordarla.
4. **Como** usuario, **quiero** buscar rápidamente una entrada por el nombre del sitio **para** encontrarla sin desplazarme por toda la lista.
5. **Como** usuario, **quiero** generar una contraseña aleatoria fuerte **para** no reutilizar contraseñas.
6. **Como** usuario, **quiero** copiar la contraseña al portapapeles **para** pegarla en el sitio sin verla en pantalla.
7. **Como** usuario, **quiero** organizar mis entradas en carpetas (p. ej. "Trabajo", "Personal", "Bancos") **para** mantener orden.
8. **Como** usuario, **quiero** que la app se bloquee sola tras un rato de inactividad **para** protegerme si dejo el equipo desatendido.
9. **Como** usuario, **quiero** editar o eliminar una entrada existente **para** mantener mis datos actualizados.

## 8. Modelo conceptual de datos (no técnico)

- **Bóveda (Vault):** el contenedor cifrado completo. Tiene metadatos de cifrado (salt, parámetros) y una colección de entradas y carpetas.
- **Carpeta (Folder):** nombre; agrupa entradas. Una entrada pertenece a una carpeta (o a "Sin carpeta").
- **Entrada (Entry):** sitio/URL, nombre de usuario, contraseña, notas, fecha de creación y de modificación.

## 9. Reglas de negocio

- Sin la contraseña maestra correcta, **no existe forma de recuperar** el contenido (es intencional: no hay "olvidé mi contraseña").
- Eliminar una carpeta debe pedir confirmación y definir qué pasa con sus entradas (mover a "Sin carpeta" o eliminar). → *ver Preguntas abiertas.*
- El generador nunca debe producir una contraseña vacía ni que incumpla las opciones marcadas.

## 10. Criterios de aceptación (alto nivel)

- Crear una bóveda, cerrar la app y volver a abrirla **solo** funciona con la contraseña maestra correcta.
- Una entrada agregada persiste tras cerrar y reabrir.
- La búsqueda devuelve resultados coherentes mientras se escribe.
- El archivo de bóveda en disco **no muestra** contraseñas legibles si se abre con un editor de texto.
- Copiar una contraseña la coloca en el portapapeles y (si está activado) se borra tras el tiempo configurado.

## 11. Fuera de alcance (v1)

- Sincronización en la nube o entre dispositivos.
- Compartir contraseñas con otras personas.
- Autocompletado en navegadores / extensiones.
- Recuperación de contraseña maestra.
- Aplicación móvil.

## 12. Preguntas abiertas `[NEEDS CLARIFICATION]`

Estas se resolverán con `/speckit.clarify` antes de planificar (ver Manual):

1. ¿La app es de **escritorio nativa**, **web local** o **terminal/CLI**? (afecta al Plan, no a la idea).
2. ¿Una sola bóveda por instalación o varias bóvedas/archivos?
3. Al **eliminar una carpeta**, ¿sus entradas se mueven a "Sin carpeta" o se borran?
4. ¿Cuántos **segundos** por defecto para el auto-bloqueo y el borrado de portapapeles?
5. ¿Se requiere soporte de **varios idiomas** o solo español en la v1?

## 13. Cómo se usa este documento

Este `.md` es la entrada para la fase de **Especificación** de Spec-Driven Development. En el *Manual* verás cómo pegar su contenido en el comando `/speckit.specify` dentro de VS Code con GitHub Copilot, para que el agente genere la especificación formal (`spec.md`) trazable a estas ideas.
