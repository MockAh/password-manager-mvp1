# IDEA — Cambiar la Contraseña Maestra (Rotación de la Maestra)

> **Documento primigenio (semilla) del ciclo `002-…`.** Captura *qué* feature queremos añadir y *por qué*, sin decidir todavía detalles de implementación. Es la entrada que alimentará el comando `/speckit.specify` de Spec Kit en una **rama nueva e independiente** (`002-change-master-password`), sobre el proyecto ya existente `001-local-password-manager`.
>
> **No reabre el núcleo.** Esta feature se apoya entera en el núcleo criptográfico de `001` —ya probado al 100 % de cobertura— y **no introduce criptografía nueva**. Respeta la misma `constitution.md` (los cuatro principios de seguridad NON-NEGOTIABLE siguen vigentes sin excepción).

---

## 0. Relación con el proyecto existente (encuadre del ciclo)

- **Base:** `001-local-password-manager` (MVP/v1). Reutiliza tal cual: derivación de llave **Argon2id** (`argon2-cffi`), cifrado autenticado **AES-256-GCM** (`cryptography`), **AAD anti-degradación** introducido por la auditoría de `001`, **escritura atómica** (temp + reemplazo) y la separación en capas (`crypto / vault / generator / ui`).
- **Naturaleza de la feature:** lógica de aplicación sobre primitivas ya existentes. **No se escribe ni se reinventa ninguna primitiva criptográfica.** Si algo tienta a "tocar el cifrado", es señal de que el diseño está mal.
- **Rama y trazabilidad:** ciclo SDD completo y propio (`002`), con su `spec.md`, `clarify`, `plan`, `tasks`, `implement`. La constitución de seguridad es la misma ancla.

---

## 1. Resumen en una frase

Permitir que el usuario, **con la bóveda desbloqueada y conociendo su contraseña maestra actual**, la sustituya por una nueva: se deriva una llave nueva con un **salt nuevo**, se **re-cifra toda la bóveda** con esa llave y se persiste de forma **atómica**, de modo que tras el cambio **solo la maestra nueva** abre la bóveda y la antigua deja de servir.

## 2. Problema y motivación (el *por qué*)

La v1 no permite cambiar la maestra: una vez elegida, queda fija para siempre. Eso choca con la higiene de seguridad básica y deja sin salida tres situaciones reales:

- El usuario eligió una maestra **débil** al principio y quiere reforzarla.
- Sospecha que su maestra **pudo quedar expuesta** (la vio alguien, la tecleó en un equipo dudoso) y necesita rotarla.
- Simplemente quiere **rotar periódicamente** por buena práctica.

**Aclaración clave (no contradice la constitución).** El principio "**no hay recuperación de la maestra**" sigue intacto. Esto **no es recuperación**: recuperación sería acceder a la bóveda *sin* conocer la maestra. Aquí es **rotación**, y **exige conocer la maestra actual**. Quien no la sepa, sigue sin poder entrar ni cambiar nada. La feature cambia la llave; no abre una puerta trasera.

## 3. Objetivo principal

Cambiar la maestra **sin exponer secretos**, **sin posibilidad de corromper la bóveda** ante una interrupción, y **sin debilitar** en ningún punto el esquema criptográfico heredado de `001`.

## 4. Usuarios objetivo

- El mismo **usuario individual** de `001`, no técnico, en un equipo personal.
- La operación ocurre **dentro de una sesión con la bóveda ya desbloqueada** (es el único contexto en que tiene sentido conocer la maestra actual).

## 5. Alcance funcional (el *qué*), priorizado

Se usa **MoSCoW**: *Must* (imprescindible para esta feature), *Should* (deseable), *Could* (futuro).

### Must — la feature
- **Punto de entrada en la UI** accesible solo con la bóveda **desbloqueada** (p. ej. menú/ajustes; ubicación a confirmar en *clarify*).
- **Exigir la maestra ACTUAL** y verificarla antes de proceder (re-autenticación explícita, no basta con que la sesión esté abierta).
- **Pedir la NUEVA maestra dos veces** (campo + confirmación) y validar que coinciden.
- **Derivar la llave nueva con un SALT NUEVO** generado aleatoriamente para esta rotación (ver §6, sutileza 1).
- **Re-cifrar la bóveda completa** (todas las entradas y carpetas) con la llave nueva.
- **Persistir de forma ATÓMICA** (temp + reemplazo), de modo que una interrupción nunca deje la bóveda a medias (ver §6, sutileza 2).
- **Re-firmar los metadatos como AAD** (salt nuevo, parámetros KDF, versión) heredando la corrección anti-degradación de `001` (ver §6, sutileza 3).
- **Limpiar de memoria** la maestra actual, la maestra nueva y **ambas** llaves en cuanto dejen de necesitarse (ver §6, sutileza 4).
- **Resultado claro:** éxito visible; en caso de fallo, mensaje seguro y **archivo intacto**.

### Should
- **Indicador de fortaleza** de la nueva maestra mientras se escribe (reusa el criterio de `001` si existe).
- **Mostrar/ocultar** los campos de contraseña.
- **Rechazar** que la nueva maestra sea idéntica a la actual (a confirmar en *clarify*).
- Definir el comportamiento de sesión tras el éxito: mantener desbloqueada o forzar re-desbloqueo con la nueva (a confirmar en *clarify*).

### Could (fuera de esta feature, anotado para el futuro)
- Aprovechar la rotación para **subir los parámetros de la KDF** (mayor factor de costo) si el hardware mejoró.
- Guardar un dato no sensible de **"fecha del último cambio de maestra"** en los metadatos.
- Rotación con **archivo de bóveda cerrado** (rotar aportando la maestra sin abrir la app) — probablemente innecesario y mayor superficie; queda fuera.

## 6. Requisitos no funcionales — **la seguridad sigue mandando**

> Mismo peso (o mayor) que lo funcional. Cualquier conflicto se resuelve a favor de la seguridad y de "la menor superficie de ataque gana".

Reglas generales heredadas de `001` que esta feature **no** puede romper: cero red y cero telemetría (todo offline); los secretos descifrados **nunca** se escriben sin cifrar; errores seguros (no filtrar nada ante maestra incorrecta o archivo dañado); **sin** recuperación de la maestra.

### El corazón técnico: las cuatro sutilezas que la spec y las tareas DEBEN capturar

Aquí es justo donde un agente descuidado metería la pata. La especificación, el plan y las tareas tienen que tratar cada uno de estos puntos como requisito explícito, con su criterio de aceptación:

1. **Salt nuevo en cada rotación — nunca reutilizar.** Cada cambio de maestra genera un **salt aleatorio nuevo** para la KDF; queda **prohibido reutilizar el salt anterior**. (Como AES-GCM exige unicidad de nonce por llave, el re-cifrado usa además un **nonce nuevo**.) Reusar el salt anularía parte del beneficio de rotar y es mala higiene.

2. **Re-cifrado atómico — interrupción → estado consistente, jamás corrupto.** Se escribe en archivo temporal y se reemplaza al final; el **punto de "commit" es el reemplazo**. Antes del commit, la bóveda **vieja sigue intacta y desbloqueable con la maestra antigua**; después, queda la nueva. En **ningún** instante puede existir un archivo a medio escribir que se confunda con la bóveda válida. No deben quedar restos del temporal.

3. **Anti-degradación vía AAD — hereda la corrección de `001`.** Los metadatos del archivo nuevo (salt, **parámetros de la KDF**, versión) se autentican como **AAD** igual que en `001`. Manipular cualquiera de ellos —en particular **bajar el costo de la KDF**— debe provocar un **fallo de descifrado**. La rotación **re-vincula** la AAD a los metadatos nuevos; nunca la omite ni la deja apuntando a los viejos.

4. **Higiene de memoria — limpiar maestra y llave viejas (y la nueva).** La rotación es una ventana de riesgo elevada porque sostiene **dos** maestras y **dos** llaves a la vez. Hay que **minimizar su tiempo de vida** y **limpiarlas** (la maestra actual, la nueva en claro, la llave vieja y la nueva) en cuanto dejen de hacer falta, al terminar, al fallar o al bloquear.

### Otros no funcionales

- **Sin copia bajo la maestra vieja:** al terminar, no debe quedar en disco ninguna copia descifrada ni ninguna copia cifrada **bajo la maestra antigua** (más allá de lo estrictamente transitorio para la atomicidad, que se elimina al completar). Si el usuario rota porque teme que la maestra vieja se filtró, dejar una copia descifrable con esa maestra anularía el propósito.
- **Rendimiento:** la derivación Argon2id es deliberadamente costosa; el re-cifrado de bóvedas de hasta **~1.000 entradas** debe completarse en un tiempo aceptable y con realimentación si tarda.
- **Usabilidad:** flujo corto y mensajes claros; un error de tecleo (confirmación que no coincide) no debe poder bloquear al usuario fuera de su bóveda.

## 7. Historias de usuario

1. **Como** usuario con la bóveda desbloqueada, **quiero** cambiar mi maestra introduciendo la actual y una nueva, **para** rotar mi llave sin perder mis datos.
2. **Como** usuario, **quiero** que me exijan la **maestra actual** aunque la bóveda esté abierta, **para** que nadie que se siente frente a mi equipo desbloqueado pueda cambiármela.
3. **Como** usuario, **quiero** confirmar la nueva maestra **dos veces**, **para** no quedarme fuera por una errata.
4. **Como** usuario, **quiero** que si el cambio se **interrumpe** (corte de luz, cierre forzado) mi bóveda **no quede corrupta**, **para** no perder mis credenciales.
5. **Como** usuario, **quiero** que tras el cambio la maestra **antigua deje de funcionar** y solo sirva la nueva, **para** que la rotación sea efectiva.
6. **(Should) Como** usuario, **quiero** ver la **fortaleza** de mi nueva maestra mientras la escribo, **para** elegir una buena.

## 8. Modelo conceptual de datos (no técnico)

- **No se crean entidades nuevas.** La feature toca los **metadatos de la Bóveda**: el **salt** (cambia), los **parámetros de la KDF** (pueden cambiar si se decide subir el costo), la **versión** y la **vinculación AAD** (se re-firma).
- **Entradas y carpetas:** su **contenido no cambia**; solo se **vuelven a cifrar** bajo la llave nueva.

## 9. Reglas de negocio

- Para cambiar la maestra **hay que conocer la actual**; sin ella, no se puede (coherente con "no recovery").
- Un **salt no se reutiliza jamás** entre rotaciones.
- Si la **maestra actual es incorrecta**, se **aborta sin tocar** el archivo (queda byte-idéntico).
- La operación es **todo-o-nada**: o se completa entera, o no cambia nada.
- Tras el éxito, la **maestra vieja queda invalidada** de facto (el archivo se re-cifró con la llave nueva; la vieja ya no descifra).
- El **generador y el resto de funciones** de `001` no se ven afectados.

## 10. Criterios de aceptación (alto nivel)

- Cambiar la maestra, cerrar la app y reabrir → **solo la nueva** desbloquea; la **vieja falla**.
- **Interrumpir** el proceso a mitad (simulado) → al reabrir, la bóveda **sigue desbloqueable** (con la vieja si no se llegó al commit, con la nueva si sí) y **nunca** aparece corrupta.
- Tras la rotación, abrir el archivo con un editor → **no muestra nada legible** y el **salt de los metadatos es distinto** al anterior.
- **Maestra actual incorrecta** → error claro y archivo **intacto (byte-idéntico)**.
- **Manipular los metadatos** del archivo nuevo (p. ej. bajar parámetros KDF) → el **descifrado falla** (AAD).
- **(Higiene)** Al terminar **no quedan** en disco copias descifradas ni copias cifradas **bajo la maestra vieja**, ni archivos temporales residuales.

## 11. Fuera de alcance (de esta feature)

- **Recuperación** de la maestra (sigue sin existir, por diseño).
- Cambiar la maestra **sin** conocer la actual.
- Rotación **programada/automática**.
- Multi-bóveda, sincronización o cambio del **algoritmo** de cifrado (a lo sumo, opcionalmente, sus **parámetros de costo**).

## 12. Preguntas abiertas `[NEEDS CLARIFICATION]`

A resolver con `/speckit.clarify` **antes** de planificar:

1. ¿La función **re-pide la maestra actual** aunque la sesión esté abierta? (recomendado: **sí**).
2. Tras una rotación exitosa, ¿se **mantiene la sesión** desbloqueada o se **fuerza re-desbloqueo** con la nueva?
3. ¿Se **rechaza** que la nueva maestra sea **idéntica** a la actual? ¿Se exige una **fortaleza mínima**?
4. ¿La rotación **conserva** los parámetros KDF actuales o permite **subirlos** de paso?
5. ¿Dónde **vive la entrada de UI** (menú principal, pantalla de ajustes, diálogo propio)?
6. **Atomicidad:** ¿semántica exacta ante interrupción? Definir con precisión el **punto de commit** (reemplazo del archivo) y qué se garantiza antes y después.

## 13. Cómo se usa este documento

Es la entrada de la fase de **Especificación** del ciclo `002`. En una **rama nueva**, pega su contenido tras `/speckit.specify` (en VS Code + GitHub Copilot, con el entorno ya listo: Python, `uv`, `specify`). Luego sigue el flujo de siempre: `/speckit.clarify` → `/speckit.plan` (que **reusa** la criptografía de `001`, sin reinventar) → `/speckit.tasks` → `/speckit.analyze` (recomendado, para que las cuatro sutilezas queden cubiertas) → `/speckit.implement`. La `constitution.md` sigue siendo el ancla; los cuatro principios de seguridad no se negocian.
