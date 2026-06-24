"""Generador de contraseñas seguras — solo stdlib secrets (T026).

Responsabilidades:
  - Generar contraseñas con longitud y conjuntos de caracteres configurables.
  - Usar exclusivamente secrets.choice — nunca random (Constitución Principio I).
  - Exponer generate_password() como única API pública del módulo.

Refs: spec.md → FR-014 (generador configurable, longitud 8–128, cuatro charsets),
               US4 Acceptance Scenarios 1–4.
      plan.md → src/generator/password_generator.py — sin dependencias de Tkinter.
      Constitución: Principio I (seguridad por diseño), II (offline, sin deps externas).
"""
import secrets
import string

# ── Conjuntos de caracteres configurables (FR-014) ────────────────────────────

UPPERCASE: str = string.ascii_uppercase          # A–Z  (26 caracteres)
LOWERCASE: str = string.ascii_lowercase          # a–z  (26 caracteres)
DIGITS: str = string.digits                      # 0–9  (10 caracteres)
SYMBOLS: str = r"!@#$%^&*()-_=+[]{}|;:,.<>?"    # símbolos imprimibles comunes (26 caracteres)

# ── Límites de longitud (FR-014) ──────────────────────────────────────────────

LENGTH_MIN: int = 8
LENGTH_MAX: int = 128


def generate_password(
    length: int,
    use_uppercase: bool = True,
    use_lowercase: bool = True,
    use_digits: bool = True,
    use_symbols: bool = False,
) -> str:
    """Genera una contraseña aleatoria segura.

    Usa secrets.choice sobre la unión de los conjuntos de caracteres habilitados.
    Nunca usa el módulo random.

    Args:
        length:        Longitud de la contraseña. Rango válido: [LENGTH_MIN, LENGTH_MAX].
        use_uppercase: Incluir letras mayúsculas (A–Z).
        use_lowercase: Incluir letras minúsculas (a–z).
        use_digits:    Incluir dígitos (0–9).
        use_symbols:   Incluir símbolos (!@#…).

    Returns:
        Cadena de `length` caracteres elegidos aleatoriamente con secrets.choice.

    Raises:
        ValueError: Si ``length`` está fuera de [LENGTH_MIN, LENGTH_MAX].
                    Ref: FR-014 — límites configurables 8–128.
        ValueError: Si ningún charset está activo (no hay caracteres de donde elegir).
                    Ref: FR-014 — al menos un conjunto debe estar habilitado.
    """
    if not (LENGTH_MIN <= length <= LENGTH_MAX):
        raise ValueError(
            f"La longitud debe estar entre {LENGTH_MIN} y {LENGTH_MAX}; recibido: {length}."
        )

    charset: str = ""
    if use_uppercase:
        charset += UPPERCASE
    if use_lowercase:
        charset += LOWERCASE
    if use_digits:
        charset += DIGITS
    if use_symbols:
        charset += SYMBOLS

    if not charset:
        raise ValueError(
            "Al menos un conjunto de caracteres debe estar habilitado."
        )

    return "".join(secrets.choice(charset) for _ in range(length))
