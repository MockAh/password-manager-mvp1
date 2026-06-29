# Gestor de Contraseñas

Aplicación de escritorio **local y offline** para guardar credenciales en un único archivo cifrado, protegido por una contraseña maestra. No usa servidores, no se conecta a la red y no almacena la contraseña maestra en ningún lado: la seguridad y la privacidad mandan sobre todo lo demás.

Desarrollado con **Spec-Driven Development (SDD)** usando Spec Kit. Todo el código se rastrea hasta una especificación escrita; el detalle del método está en `Reporte_SDD_Gestor_Contrasenas.md`.

---

## Características

- **Bóveda cifrada** en un solo archivo, protegida por contraseña maestra.
- **Gestión de credenciales:** crear, editar, eliminar y buscar entradas (título, usuario, contraseña, URL, notas).
- **Búsqueda en tiempo real** por título y usuario.
- **Organización por carpetas;** al eliminar una carpeta, sus entradas se conservan y pasan a "Sin carpeta".
- **Generador de contraseñas** con longitud y conjuntos de caracteres configurables, basado en aleatoriedad criptográficamente segura.
- **Copia al portapapeles** con borrado automático tras un tiempo configurable.
- **Auto-bloqueo por inactividad;** cualquier actividad del usuario reinicia el temporizador.
- **Cambio de la contraseña maestra (rotación):** desde la bóveda desbloqueada, el usuario puede sustituir su contraseña maestra conociendo la actual. La operación genera un salt nuevo, re-cifra la bóveda completa y la persiste de forma atómica; tras el cambio, solo la contraseña nueva abre la bóveda. No es un mecanismo de recuperación: exige conocer la maestra actual, por lo que respeta el principio de "no hay recuperación".
- **Configuración** de los tiempos de portapapeles y auto-bloqueo.

---

## Requisitos

- **Python 3.11 o superior.**
- **Tkinter** (incluido con la mayoría de instalaciones de Python; en algunas distribuciones de Linux se instala aparte con `sudo apt install python3-tk`).

---

## Instalación

Se recomienda usar un entorno virtual.

```bash
# 1. Clonar el repositorio
git clone https://github.com/MockAh/password-manager-mvp1.git
cd password-manager-mvp1

# 2. Crear y activar un entorno virtual
python -m venv .venv
source .venv/bin/activate        # Linux / macOS / WSL
# .venv\Scripts\activate         # Windows (PowerShell)

# 3. Instalar el proyecto y sus dependencias
pip install -e .
```

El comando `pip install -e .` lee el archivo `pyproject.toml` e instala las dependencias de producción (`argon2-cffi` y `cryptography`).

Para incluir además las herramientas de desarrollo (pruebas y cobertura):

```bash
pip install -e ".[dev]"
```

---

## Uso

Con el entorno virtual activado, desde la raíz del proyecto:

```bash
python -m src.main
```

Al iniciar, la aplicación muestra la pantalla de desbloqueo:

- **Primera vez:** usa **"Crear nueva bóveda"**, define la contraseña maestra y elige dónde guardar el archivo cifrado.
- **Usos posteriores:** selecciona el archivo de bóveda con **"Examinar…"**, escribe la contraseña maestra y pulsa **"Desbloquear"**.

### Cambiar la contraseña maestra

Con la bóveda desbloqueada, pulsa **"🔑 Cambiar maestra…"** en la barra de acciones de la vista principal. Se abre un diálogo que pide la **contraseña actual** (re-autenticación obligatoria, aunque la sesión esté abierta), la **contraseña nueva** y su **confirmación**. La nueva debe tener al menos 12 caracteres y no puede ser idéntica a la actual. Al confirmar, la bóveda se re-cifra con la nueva llave y queda lista para seguir usándose.

> **Importante:** la contraseña maestra no se puede recuperar. Si se olvida, se pierde el acceso a todos los datos de forma permanente. No existe mecanismo de recuperación, por diseño. El cambio de maestra **no** es una excepción a esto: requiere conocer la contraseña actual.

---

## Pruebas

El proyecto incluye una suite de pruebas unitarias y de integración.

```bash
# Ejecutar todas las pruebas
python -m pytest

# Cobertura del módulo criptográfico
python -m pytest --cov=src/crypto --cov-report=term-missing

# Cobertura del servicio de bóveda (incluye la rotación de maestra)
python -m pytest --cov=src/vault/service --cov-report=term-missing
```

La suite completa pasa **196 pruebas**. El módulo criptográfico mantiene una cobertura del **100 %** y el servicio de bóveda (`vault/service.py`) del **96 %**, ambos por encima del umbral mínimo del 95 % definido en la constitución del proyecto. La capa de interfaz (`ui/`) se excluye de la medición de cobertura de forma intencional, ya que se valida manualmente con los escenarios de `quickstart.md`.

---

## Arquitectura

El proyecto separa la lógica de la interfaz en capas:

```
src/
├── crypto/        Derivación de llave (Argon2id) y cifrado de bóveda (AES-256-GCM)
├── vault/         Modelos, repositorio, servicio de bóveda y excepciones
├── generator/     Generador de contraseñas (módulo `secrets`)
├── ui/            Interfaz Tkinter (vistas, app, portapapeles, diálogo de cambio de maestra)
└── main.py        Punto de entrada
```

**Decisiones técnicas principales:**

| Componente | Elección | Motivo |
|---|---|---|
| Interfaz | Tkinter | Librería estándar de Python; sin dependencias gráficas externas |
| Derivación de llave | Argon2id (`argon2-cffi`) | Memory-hard, resistente a fuerza bruta |
| Cifrado | AES-256-GCM (`cryptography`) | Cifrado autenticado; detecta manipulación del archivo |
| Generador | módulo `secrets` | Aleatoriedad criptográficamente segura del sistema operativo |
| Persistencia | Escritura atómica (archivo temporal + reemplazo) | Evita bóvedas corruptas ante fallos de disco |

Los metadatos de la bóveda (parámetros de la KDF, versión, salt) se autentican como datos adicionales (AAD), de modo que cualquier manipulación del archivo provoca un fallo de descifrado.

**Rotación de la contraseña maestra.** El cambio de maestra reutiliza íntegramente este núcleo, sin introducir criptografía nueva. Cada rotación genera un **salt nuevo** (nunca se reutiliza el anterior) y un **nonce nuevo**, re-cifra el payload completo bajo la llave derivada de la contraseña nueva, re-vincula la AAD a los metadatos nuevos (impidiendo ataques de degradación de la KDF) y persiste el resultado de forma **atómica**: una interrupción antes del reemplazo del archivo deja la bóveda anterior intacta; después, la nueva queda completa. Nunca existe un estado parcialmente escrito. La verificación de la contraseña actual se hace en memoria (comparación en tiempo constante), sin re-leer ni re-descifrar el archivo, y las llaves se limpian de memoria en cuanto dejan de necesitarse.

---

## Metodología

El proyecto se construyó con **Spec-Driven Development**: la especificación es la fuente única de verdad, las decisiones las dirige una persona y el agente redacta, y cada pieza de código se rastrea hasta una decisión consciente. El recorrido completo del MVP fundacional —constitución, especificación, clarificación, plan, auditoría, tareas e implementación— está documentado en `Reporte_SDD_Gestor_Contrasenas.md`.

La especificación, el plan, el modelo de datos, los contratos y las tareas del proyecto base viven en `specs/001-local-password-manager/`.

La funcionalidad de **cambio de contraseña maestra** se desarrolló como un ciclo SDD independiente, con su propia especificación, clarificación, plan, auditoría (`/speckit.analyze`) e implementación, y sus artefactos viven en `specs/002-change-master-password/`. La auditoría del ciclo detectó y corrigió, antes de escribir código de producción, una contradicción entre la especificación y el plan y la ausencia de una prueba de seguridad; la validación manual confirmó el flujo de punta a punta (incluido el reinicio de la aplicación para verificar que solo la contraseña nueva abre la bóveda).

---

## Limitaciones conocidas y trabajo futuro

Estas observaciones se detectaron durante la validación y se documentan de forma deliberada. No comprometen la seguridad de la bóveda.

- **Portapapeles en WSL:** el pegado hacia aplicaciones de Windows puede no funcionar por una limitación del puente de portapapeles entre WSL y Windows. La copia, el aviso visual y el borrado automático funcionan correctamente. Conviene re-validar el pegado externo en un entorno no-WSL.
- **Borrado del portapapeles:** el borrado automático limpia el portapapeles al cumplirse el tiempo sin verificar si el contenido sigue siendo el copiado. Es un detalle de experiencia de uso, no de seguridad.
- **Auto-bloqueo con formulario abierto:** si la bóveda se auto-bloquea con un formulario de entrada abierto y datos sin guardar, esos datos se pierden sin aviso. El binding de actividad evita el bloqueo durante el uso activo, pero no cubre el caso de un formulario abierto sin interacción.
- **Diálogo de cambio de maestra abandonado:** durante la operación de cambio de maestra el auto-bloqueo se suspende; teclear en los campos cuenta como actividad. Sin embargo, si el diálogo se abre y se abandona sin pulsar "Confirmar", el temporizador de inactividad corre con normalidad y puede bloquear la bóveda con el diálogo abierto. No hay riesgo de corrupción (la operación aún no había comenzado).
- **Higiene de memoria en CPython:** las llaves derivadas se almacenan en `bytearray` y se sobreescriben a ceros en cuanto dejan de necesitarse. Sin embargo, los objetos `str` de las contraseñas son inmutables en CPython y no pueden borrarse explícitamente (se mitiga liberando referencias), y los buffers internos de la biblioteca Argon2 quedan fuera del control de Python. La limpieza es la máxima posible dentro de la plataforma.
- **Cobertura de la interfaz:** la capa de UI no tiene pruebas automatizadas (se excluye de la cobertura); se valida manualmente.
- **Interfaz gráfica en WSL:** la aplicación es Tkinter puro y multiplataforma, pero ejecutarla bajo WSL requiere un servidor gráfico (WSLg en Windows 11). Si WSLg queda en mal estado, la ventana puede no aparecer; un reinicio limpio con `wsl --shutdown` desde PowerShell suele resolverlo. La validación de la interfaz en un entorno con pantalla nativa (Windows, Linux de escritorio o macOS) es la más fiable.

Las funcionalidades nuevas se abordan como ciclos SDD independientes en su propia rama, respetando la misma constitución de seguridad.
