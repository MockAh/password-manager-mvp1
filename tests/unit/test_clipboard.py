"""Tests unitarios del módulo clipboard (T029).

Las pruebas mockean el objeto tk.Tk (no se necesita display) y threading.Timer
(no hay esperas de tiempo real) para ser deterministas y rápidos.

Refs: spec.md → FR-015 (copiar al portapapeles), FR-016 (borrado automático),
               FR-022 (borrado inmediato al bloquear), US5 Acceptance Scenarios 1–3.
      tasks.md → T029.
"""
import threading
from unittest.mock import MagicMock, call, patch

import pytest


# ── Fixture: raíz Tk simulada ─────────────────────────────────────────────────


class _FakeRoot:
    """Simulacro de tk.Tk: registra operaciones de portapapeles y after()."""

    def __init__(self):
        self._clipboard: str = ""
        self.after_calls: list[tuple[int, object]] = []

    def clipboard_clear(self) -> None:
        self._clipboard = ""

    def clipboard_append(self, value: str) -> None:
        self._clipboard += value

    def after(self, delay_ms: int, callback) -> None:
        """Ejecuta el callback de forma síncrona (tests deterministas)."""
        self.after_calls.append((delay_ms, callback))
        callback()


@pytest.fixture(autouse=True)
def reset_clipboard_state():
    """Resetea el estado de módulo de clipboard entre tests."""
    import ui.clipboard as cb
    cb._cancel_timer()          # asegurar que no queda timer de otro test
    yield
    cb._cancel_timer()


# ── copy_to_clipboard ─────────────────────────────────────────────────────────


class TestCopyToClipboard:
    """copy_to_clipboard coloca valor y arranca timer.

    Refs: FR-015, FR-016, US5 Acceptance Scenarios 1–2.
    """

    def test_sets_clipboard_value(self):
        """El valor se copia al portapapeles.
        Ref: FR-015; US5 Acceptance Scenario 1."""
        import ui.clipboard as cb
        root = _FakeRoot()
        with patch.object(cb, "_start_timer"):  # no iniciar timer real
            cb.copy_to_clipboard(root, "s3cr3t", clear_after_s=20)
        assert root._clipboard == "s3cr3t"

    def test_starts_timer_with_correct_delay(self):
        """Se inicia un threading.Timer con el delay indicado.
        Ref: FR-016 — borrado tras timeout configurable."""
        import ui.clipboard as cb
        root = _FakeRoot()
        with patch("ui.clipboard.threading.Timer") as mock_timer_cls:
            mock_timer = MagicMock()
            mock_timer_cls.return_value = mock_timer
            cb.copy_to_clipboard(root, "pwd", clear_after_s=30)

        mock_timer_cls.assert_called_once_with(30, cb._do_clear, args=[root])
        mock_timer.start.assert_called_once()

    def test_cancels_previous_timer_before_new_copy(self):
        """Un segundo copy cancela el timer anterior.
        Ref: FR-016 — una sola copia activa en todo momento."""
        import ui.clipboard as cb
        root = _FakeRoot()
        with patch("ui.clipboard.threading.Timer") as mock_timer_cls:
            first_timer = MagicMock()
            second_timer = MagicMock()
            mock_timer_cls.side_effect = [first_timer, second_timer]

            cb.copy_to_clipboard(root, "first", clear_after_s=20)
            cb.copy_to_clipboard(root, "second", clear_after_s=20)

        first_timer.cancel.assert_called_once()
        second_timer.start.assert_called_once()

    def test_zero_delay_does_not_start_timer(self):
        """clear_after_s=0 desactiva el timer (C-004 edge case).
        Ref: spec.md Clarifications — timeout 0 deshabilita el borrado automático."""
        import ui.clipboard as cb
        root = _FakeRoot()
        with patch("ui.clipboard.threading.Timer") as mock_timer_cls:
            cb.copy_to_clipboard(root, "pwd", clear_after_s=0)
        mock_timer_cls.assert_not_called()
        assert root._clipboard == "pwd"

    def test_default_delay_is_20_seconds(self):
        """El delay por defecto es 20 segundos (C-004, FR-016).
        Ref: spec.md → C-004 — timeout portapapeles 20 s."""
        import ui.clipboard as cb
        root = _FakeRoot()
        with patch("ui.clipboard.threading.Timer") as mock_timer_cls:
            mock_timer = MagicMock()
            mock_timer_cls.return_value = mock_timer
            cb.copy_to_clipboard(root, "pwd")  # sin clear_after_s → default

        delay_arg = mock_timer_cls.call_args[0][0]
        assert delay_arg == 20

    def test_clears_before_appending(self):
        """clipboard_clear() se llama antes de clipboard_append().
        Evita acumulación si había contenido previo."""
        import ui.clipboard as cb
        root = _FakeRoot()
        root.clipboard_append("anterior")  # simular contenido previo
        with patch.object(cb, "_start_timer"):
            cb.copy_to_clipboard(root, "nuevo", clear_after_s=0)
        assert root._clipboard == "nuevo"


# ── cancel_clipboard_timer ────────────────────────────────────────────────────


class TestCancelClipboardTimer:
    """cancel_clipboard_timer borra el portapapeles inmediatamente y cancela timer.

    Refs: FR-022 (borrado inmediato al bloquear), US5 Acceptance Scenario 3.
    """

    def test_clears_clipboard_immediately(self):
        """El portapapeles se limpia de inmediato al cancelar.
        Ref: FR-022 — borrado inmediato al bloquear la bóveda."""
        import ui.clipboard as cb
        root = _FakeRoot()
        root.clipboard_append("secreto")
        cb.cancel_clipboard_timer(root)
        assert root._clipboard == ""

    def test_cancels_pending_timer(self):
        """El timer pendiente se cancela al llamar cancel_clipboard_timer.
        Ref: FR-022; US5 Acceptance Scenario 3 — bloquear antes del timeout."""
        import ui.clipboard as cb
        root = _FakeRoot()
        with patch("ui.clipboard.threading.Timer") as mock_timer_cls:
            mock_timer = MagicMock()
            mock_timer_cls.return_value = mock_timer
            cb.copy_to_clipboard(root, "secreto", clear_after_s=20)

        cb.cancel_clipboard_timer(root)
        mock_timer.cancel.assert_called_once()

    def test_safe_when_no_timer_active(self):
        """No lanza excepción si no hay timer activo."""
        import ui.clipboard as cb
        root = _FakeRoot()
        cb.cancel_clipboard_timer(root)  # sin timer previo — no debe lanzar
        assert root._clipboard == ""


# ── _do_clear ─────────────────────────────────────────────────────────────────


class TestDoClear:
    """_do_clear despacha el borrado al hilo Tk vía root.after(0, ...).

    Ref: thread-safety — Timer corre en hilo auxiliar; Tkinter no es thread-safe.
    """

    def test_do_clear_dispatches_via_after(self):
        """_do_clear llama a root.after(0, root.clipboard_clear).
        Garantiza que el borrado ocurre en el hilo principal de Tk."""
        import ui.clipboard as cb
        root = _FakeRoot()
        root.clipboard_append("contenido")
        cb._do_clear(root)
        # _FakeRoot.after ejecuta el callback síncronamente
        assert root._clipboard == ""
        assert len(root.after_calls) == 1
        delay_ms, _ = root.after_calls[0]
        assert delay_ms == 0
