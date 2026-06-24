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

> **Importante:** la contraseña maestra no se puede recuperar. Si se olvida, se pierde el acceso a todos los datos de forma permanente. No existe mecanismo de recuperación, por diseño.

---

## Pruebas

El proyecto incluye una suite de pruebas unitarias y de integración.

```bash
# Ejecutar todas las pruebas
python -m pytest

# Ejecutar con reporte de cobertura del módulo criptográfico
python -m pytest --cov=src/crypto --cov-report=term-missing
```

El módulo criptográfico mantiene una cobertura del 100 % (el umbral mínimo definido en la constitución del proyecto es 95 %). La capa de interfaz (`ui/`) se excluye de la medición de cobertura de forma intencional, ya que se valida manualmente.

---

## Arquitectura

El proyecto separa la lógica de la interfaz en capas:

```
src/
├── crypto/        Derivación de llave (Argon2id) y cifrado de bóveda (AES-256-GCM)
├── vault/         Modelos, repositorio, servicio de bóveda y excepciones
├── generator/     Generador de contraseñas (módulo `secrets`)
├── ui/            Interfaz Tkinter (vistas, app, portapapeles)
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

---

## Metodología

El proyecto se construyó con **Spec-Driven Development**: la especificación es la fuente única de verdad, las decisiones las dirige una persona y el agente redacta, y cada pieza de código se rastrea hasta una decisión consciente. El recorrido completo —constitución, especificación, clarificación, plan, auditoría, tareas e implementación— está documentado en `Reporte_SDD_Gestor_Contrasenas.md`.

La especificación, el plan, el modelo de datos, los contratos y las tareas viven en `specs/001-local-password-manager/`.

---

## Limitaciones conocidas y trabajo futuro

Estas observaciones se detectaron durante la validación y se documentan de forma deliberada. No comprometen la seguridad de la bóveda.

- **Portapapeles en WSL:** el pegado hacia aplicaciones de Windows puede no funcionar por una limitación del puente de portapapeles entre WSL y Windows. La copia, el aviso visual y el borrado automático funcionan correctamente. Conviene re-validar el pegado externo en un entorno no-WSL.
- **Borrado del portapapeles:** el borrado automático limpia el portapapeles al cumplirse el tiempo sin verificar si el contenido sigue siendo el copiado. Es un detalle de experiencia de uso, no de seguridad.
- **Auto-bloqueo con formulario abierto:** si la bóveda se auto-bloquea con un formulario de entrada abierto y datos sin guardar, esos datos se pierden sin aviso. El binding de actividad evita el bloqueo durante el uso activo, pero no cubre el caso de un formulario abierto sin interacción.
- **Cobertura de la interfaz:** la capa de UI no tiene pruebas automatizadas (se excluye de la cobertura); se valida manualmente.

Las funcionalidades nuevas se abordarían como ciclos SDD independientes en su propia rama, respetando la misma constitución de seguridad.
