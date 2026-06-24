# Reporte de proyecto — Gestor de Contraseñas con Spec-Driven Development

**Proyecto:** Gestor de contraseñas local y offline (`001-local-password-manager`)
**Metodología:** Spec-Driven Development (SDD) con Spec Kit
**Entorno:** VS Code + GitHub Copilot (agente Claude/Sonnet) sobre Windows con WSL-Bash
**Herramienta:** Spec Kit `v0.10.2` (CLI `specify`)
**Estado:** MVP fundacional construido y validado · v1 en progreso

---

## 1. Resumen ejecutivo

El objetivo de este trabajo no era solo construir un gestor de contraseñas, sino **demostrar el método Spec-Driven Development** de punta a punta, usando como caso práctico una aplicación donde la seguridad es crítica.

Hasta este punto se completó todo el camino metodológico —encuadre, especificación, clarificación, plan, auditoría, tareas— y se implementó y validó el **MVP fundacional** (bóveda cifrada con creación, desbloqueo y bloqueo). El núcleo criptográfico está terminado, probado al 100 % de cobertura y la aplicación arranca correctamente. Restan las historias de usuario US2–US7 para cerrar la v1.

A lo largo del proceso, el método demostró su valor en dos momentos concretos: atrapó decisiones que el agente tomaba en silencio (la fase de clarificación) y detectó un fallo de diseño de seguridad real **antes de escribir una sola línea de código** (la fase de auditoría). Ambos episodios se detallan en la sección 4.

---

## 2. El proyecto

Una aplicación de **escritorio, local y offline** que guarda credenciales en un **único archivo cifrado** protegido por una **contraseña maestra**. Permite crear, editar, eliminar, buscar y organizar entradas por carpetas, generar contraseñas seguras y copiarlas al portapapeles. Principio rector: **la seguridad y la privacidad mandan sobre todo lo demás**; no hay servidores, ni red, ni recuperación de la contraseña maestra.

**Decisiones técnicas clave (fijadas en el Plan):**

| Componente | Elección | Motivo |
|---|---|---|
| Interfaz | Tkinter (librería estándar de Python) | Cero dependencias gráficas externas; multiplataforma |
| Derivación de llave | Argon2id (`argon2-cffi`) | Memory-hard, resistente a fuerza bruta; recomendación OWASP/NIST |
| Cifrado | AES-256-GCM (`cryptography`/PyCA) | Cifrado autenticado estándar; detecta manipulación del archivo |
| Generador | `secrets` (CSPRNG del SO) | Aleatoriedad criptográficamente segura |
| Persistencia | Escritura atómica (temp + rename) | Evita bóvedas corruptas ante fallos de disco |

---

## 3. Recorrido metodológico (fase por fase)

| Fase SDD | Comando Spec Kit | Entregable | Estado |
|---|---|---|---|
| 0. Entorno / principios | `/speckit.constitution` | `constitution.md` (v1.0.0, 8 principios) | ✅ Completo |
| 1. Especificación | `/speckit.specify` | `spec.md` (7 historias, 22 FR, 10 criterios) | ✅ Completo |
| 2. Clarificación | (corrección dirigida de supuestos) | Sección `Clarifications` (C-001…C-007) | ✅ Completo |
| 3. Plan técnico | `/speckit.plan` | `plan.md`, `research.md`, `data-model.md`, contratos | ✅ Completo |
| Auditoría | revisión del plan | Corrección de seguridad (AAD) + recorte de alcance | ✅ Completo |
| 4. Tareas | `/speckit.tasks` | `tasks.md` (41 tareas, 10 fases) | ✅ Completo |
| 5. Implementación (MVP) | `/speckit.implement` | Código + 87 tests (Fases 1–3) | ✅ Completo |
| 5. Implementación (resto) | `/speckit.implement` | US2–US7 + polish | ⏳ Pendiente |
| 6–7. Integración y entrega | prompts normales | README, empaquetado | ⏳ Pendiente |

**Encuadre (Constitución).** Antes de escribir la spec se fijaron los principios rectores. Quedaron **8 principios**, con los cuatro de seguridad marcados **NON-NEGOTIABLE** (seguridad por diseño, privacidad/offline, cifrado autenticado + derivación robusta, sin recuperación de la maestra), una jerarquía explícita de resolución de conflictos ("la menor superficie de ataque gana") y un umbral medible: cobertura de tests ≥ 95 % en el módulo criptográfico.

**Especificación.** Se generó una spec con 7 historias de usuario priorizadas (P1–P7), 22 requisitos funcionales y 10 criterios de éxito medibles y agnósticos de tecnología.

**Plan.** Aquí se decidió el stack y la arquitectura modular con la interfaz separada de la lógica (capa cripto · capa de datos · generador · UI delgada).

**Tareas.** El plan se partió en 41 tareas ordenadas por dependencias: la fundación criptográfica primero (bloqueante), luego las historias por prioridad, la UI tejida dentro de cada una.

---

## 4. Dos episodios donde SDD demostró su valor

### 4.1 Decisiones ocultas disfrazadas de "supuestos"

**Problema.** Tras generar la spec, el agente reportó "0 ambigüedades pendientes" pero a la vez registró 9 *Assumptions*. En realidad había **resuelto por su cuenta** decisiones que eran del usuario (tipo de interfaz, modelo de bóveda, borrado de carpetas, tiempos, idioma) y algunas ni siquiera quedaron cubiertas. Un supuesto silencioso es una decisión disfrazada que se propaga sin que nadie la haya elegido.

**Solución.** Se cruzaron los supuestos contra las preguntas abiertas, el usuario tomó las decisiones y se registraron como **clarificaciones fechadas y trazables** (C-001…C-007), ligadas a los requisitos e historias afectados, eliminando contradicciones.

**Lección SDD.** La sección *Clarifications* convierte cada decisión en algo explícito y rastreable. La disciplina del método es sacar a la luz las decisiones ocultas temprano, no confiar ciegamente en el resumen del agente.

### 4.2 Fallo de seguridad detectado por la auditoría

**Problema.** El plan eligió criptografía sólida (Argon2id + AES-256-GCM), pero autenticaba solo el **contenido** de la bóveda, no los **metadatos** (parámetros de la KDF, versión, salt). Un atacante con el archivo podía **bajar el costo de la KDF** sin que el cifrado lo detectara, acelerando enormemente el ataque por fuerza bruta. La constitución lo marcó: Principio III en "⚠️ Parcial".

**Solución.** Se ataron esos metadatos como **AAD** (datos autenticados adicionales) con JSON canónico, de modo que manipular cualquier campo provoca un fallo de descifrado. Se reflejó en los contratos y se re-verificó la constitución (Principio III → ✅).

**Lección SDD.** La auditoría es una fase del método, no un extra. Empuja la corrección **aguas arriba**: se arregla el diseño en la fuente de verdad antes de programar, y desde ahí baja al código de forma trazable. Corregirlo en el plan costó unas líneas; descubrirlo con la app construida habría obligado a cambiar el formato de archivo y migrar bóvedas.

---

## 5. Estado actual — MVP fundacional construido

Se implementó el slice **Fases 1–3 (tareas T001–T018)**, deteniéndose deliberadamente ahí para validar antes de seguir.

**Lo construido:**
- Módulo criptográfico: derivación de llave (Argon2id) y cifrado de bóveda (AES-256-GCM con AAD anti-downgrade).
- Capa de datos: modelos, repositorio y servicio de bóveda; manejo de errores seguro.
- Interfaz Tkinter (US1): vistas de creación, desbloqueo y principal.
- Suite de pruebas: unitarias de cripto y de bóveda, e integración con detección de manipulación.

**Métricas y validación:**

| Indicador | Resultado |
|---|---|
| Pruebas | **87/87 en verde** |
| Cobertura del módulo criptográfico | **100 %** (supera el ≥95 % de la constitución) |
| Cobertura total | 87 % |
| Arranque de la GUI (`main.py`) | ✅ La ventana abrió correctamente |
| Diagnóstico de seguridad (cero red; sin maestra/datos en logs o disco) | ✅ Sin incidencias |
| Flujo US1 (crear → cerrar → reabrir → desbloquear) | ✅ Validado de punta a punta |

El desarrollo se versionó con Git tras cada fase, permitiendo volver atrás si una iteración se desviaba.

---

## 6. Lo que falta para cerrar la v1

Restan **7 fases / 23 tareas** (T019–T041), todas apoyadas sobre el núcleo ya terminado:

| Fase | Historia | Tareas |
|---|---|---|
| 4 | US2 — CRUD de entradas | T019–T022 |
| 5 | US3 — Búsqueda en tiempo real | T023–T025 |
| 6 | US4 — Generador de contraseñas | T026–T028 |
| 7 | US5 — Portapapeles con auto-borrado | T029–T030 |
| 8 | US6 — Carpetas | T031–T034 |
| 9 | US7 — Auto-bloqueo por inactividad | T035–T037 |
| 10 | Polish (cobertura final, limpieza) | T038–T041 |

La parte de mayor riesgo (la criptografía) ya está resuelta y probada; lo restante es lógica de aplicación e interfaz sobre esa base.

**Después de la v1:** un feature nuevo (p. ej. exportar/importar o detección de contraseñas débiles) se aborda como un **ciclo SDD completo** en su propia rama (`002-…`), respetando la misma constitución de seguridad.

---

## 7. Conclusión

Hasta este punto, el proyecto cumple su doble objetivo: existe un MVP funcional y seguro, y —más importante para el propósito— se documentó **cómo SDD ordena el desarrollo**. El método mostró su retorno concreto al atrapar tanto decisiones ocultas como un fallo de seguridad real en la fase de diseño, antes de que costaran reescrituras. El principio de fondo quedó demostrado en la práctica: **la especificación es la fuente única de verdad, el humano dirige y el agente redacta, y cada pieza de código se rastrea hasta una decisión consciente.**
