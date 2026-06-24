"""Tests unitarios del generador de contraseñas (T027).

Cubre: longitud correcta, chars de charsets habilitados, unicidad sucesiva,
       boundaries (8 y 128), ValueError en casos inválidos, charset único activo.

Refs: spec.md → User Story 4, Acceptance Scenarios 1–4.
      FR-014: longitud 8–128; cuatro charsets; al menos uno activo.
      tasks.md → T027.
"""
import string

import pytest

from generator.password_generator import (
    DIGITS,
    LENGTH_MAX,
    LENGTH_MIN,
    LOWERCASE,
    SYMBOLS,
    UPPERCASE,
    generate_password,
)


# ── Longitud correcta ─────────────────────────────────────────────────────────


class TestLength:
    """La contraseña generada tiene exactamente la longitud solicitada.

    Ref: FR-014 — longitud configurable de 8 a 128 caracteres.
         US4 Acceptance Scenario 2.
    """

    def test_default_length_16(self):
        """generate_password con length=16 devuelve 16 chars."""
        pw = generate_password(16)
        assert len(pw) == 16

    def test_arbitrary_length(self):
        """Longitud arbitraria respetada exactamente."""
        for length in (8, 20, 64, 100, 128):
            assert len(generate_password(length)) == length

    def test_boundary_min(self):
        """Boundary inferior: length=8 funciona sin error.
        Ref: FR-014 — mínimo 8 caracteres."""
        pw = generate_password(LENGTH_MIN)
        assert len(pw) == LENGTH_MIN

    def test_boundary_max(self):
        """Boundary superior: length=128 funciona sin error.
        Ref: FR-014 — máximo 128 caracteres."""
        pw = generate_password(LENGTH_MAX)
        assert len(pw) == LENGTH_MAX


# ── Solo caracteres de los charsets habilitados ───────────────────────────────


class TestCharsets:
    """La contraseña solo contiene chars de los conjuntos habilitados.

    Ref: FR-014 — selección de charsets; US4 Acceptance Scenario 2.
    """

    def test_only_uppercase(self):
        """Solo mayúsculas cuando use_uppercase=True, resto False."""
        pw = generate_password(
            40, use_uppercase=True, use_lowercase=False, use_digits=False, use_symbols=False
        )
        assert all(c in UPPERCASE for c in pw)

    def test_only_lowercase(self):
        """Solo minúsculas cuando use_lowercase=True, resto False."""
        pw = generate_password(
            40, use_uppercase=False, use_lowercase=True, use_digits=False, use_symbols=False
        )
        assert all(c in LOWERCASE for c in pw)

    def test_only_digits(self):
        """Solo dígitos cuando use_digits=True, resto False."""
        pw = generate_password(
            40, use_uppercase=False, use_lowercase=False, use_digits=True, use_symbols=False
        )
        assert all(c in DIGITS for c in pw)

    def test_only_symbols(self):
        """Solo símbolos cuando use_symbols=True, resto False."""
        pw = generate_password(
            40, use_uppercase=False, use_lowercase=False, use_digits=False, use_symbols=True
        )
        assert all(c in SYMBOLS for c in pw)

    def test_digits_and_lowercase(self):
        """Combinación dígitos + minúsculas."""
        allowed = set(DIGITS + LOWERCASE)
        pw = generate_password(
            60, use_uppercase=False, use_lowercase=True, use_digits=True, use_symbols=False
        )
        assert all(c in allowed for c in pw)

    def test_all_charsets(self):
        """Todos los charsets habilitados: ningún char fuera del universo."""
        all_chars = set(UPPERCASE + LOWERCASE + DIGITS + SYMBOLS)
        pw = generate_password(
            80, use_uppercase=True, use_lowercase=True, use_digits=True, use_symbols=True
        )
        assert all(c in all_chars for c in pw)

    def test_single_charset_enabled_no_error(self):
        """Un solo charset activo no lanza error.
        Ref: tasks.md → T027 — un solo charset habilitado funciona sin error."""
        # Verifica los cuatro charsets uno a uno
        generate_password(16, use_uppercase=True, use_lowercase=False, use_digits=False, use_symbols=False)
        generate_password(16, use_uppercase=False, use_lowercase=True, use_digits=False, use_symbols=False)
        generate_password(16, use_uppercase=False, use_lowercase=False, use_digits=True, use_symbols=False)
        generate_password(16, use_uppercase=False, use_lowercase=False, use_digits=False, use_symbols=True)


# ── Unicidad sucesiva ─────────────────────────────────────────────────────────


class TestUniqueness:
    """Valores sucesivos son distintos con alta probabilidad.

    Ref: tasks.md → T027 — ≥ 99/100 llamadas únicas sobre muestra de 100.
         US4 Acceptance Scenario 4 — regenerar produce un nuevo valor diferente.
    """

    def test_successive_calls_are_distinct(self):
        """≥ 99 de 100 contraseñas de longitud 16 son distintas.

        La probabilidad de colisión con charset completo y length=16 es
        astronómicamente baja; el umbral 99/100 es conservador.
        """
        passwords = [generate_password(16) for _ in range(100)]
        unique_count = len(set(passwords))
        assert unique_count >= 99, (
            f"Se esperaban ≥ 99 contraseñas únicas; se obtuvieron {unique_count}"
        )

    def test_consecutive_pair_differs(self):
        """Dos llamadas consecutivas producen valores diferentes (probabilístico)."""
        # Con length=20 y charset completo, la probabilidad de igualdad es ~0.
        p1 = generate_password(20)
        p2 = generate_password(20)
        assert p1 != p2


# ── Errores de validación ─────────────────────────────────────────────────────


class TestValidationErrors:
    """ValueError en parámetros inválidos.

    Ref: FR-014 — longitud 8–128; al menos un charset activo.
         tasks.md → T027 — boundaries de error.
    """

    def test_length_below_min_raises(self):
        """length=7 (< LENGTH_MIN=8) lanza ValueError.
        Ref: FR-014 — mínimo 8 caracteres."""
        with pytest.raises(ValueError, match="longitud"):
            generate_password(LENGTH_MIN - 1)

    def test_length_above_max_raises(self):
        """length=129 (> LENGTH_MAX=128) lanza ValueError.
        Ref: FR-014 — máximo 128 caracteres."""
        with pytest.raises(ValueError, match="longitud"):
            generate_password(LENGTH_MAX + 1)

    def test_length_zero_raises(self):
        """length=0 lanza ValueError."""
        with pytest.raises(ValueError):
            generate_password(0)

    def test_length_negative_raises(self):
        """length negativo lanza ValueError."""
        with pytest.raises(ValueError):
            generate_password(-1)

    def test_all_charsets_false_raises(self):
        """Todos los charsets deshabilitados lanza ValueError.
        Ref: tasks.md → T027 — ValueError con todos charsets False."""
        with pytest.raises(ValueError, match="conjunto"):
            generate_password(
                16,
                use_uppercase=False,
                use_lowercase=False,
                use_digits=False,
                use_symbols=False,
            )
