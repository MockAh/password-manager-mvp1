"""Gestión del portapapeles con borrado automático (T029).

Responsabilidades:
  - Copiar un valor al portapapeles del sistema e iniciar un timer de borrado.
  - Cancelar el timer previo antes de cada nueva copia (una sola copia activa).
  - Limpiar el portapapeles inmediatamente al bloquear la bóveda (FR-022).
  - Thread-safety: _do_clear despacha la operación Tk al hilo principal via after().

Refs: spec.md → FR-015 (copiar al portapapeles), FR-016 (borrado automático tras
               timeout configurable, default 20 s), FR-022 (borrado inmediato al bloquear),
               US5 Acceptance Scenarios 1–3, SC-005 (borrado dentro del timeout).
      Constitución: Principio I — datos sensibles no persisten en el portapapeles
                    más tiempo del necesario.

API pública:
    copy_to_clipboard(root, value, clear_after_s=20)
    cancel_clipboard_timer(root)
"""
import threading
import tkinter as tk
from typing import Optional

# ── Estado de módulo ──────────────────────────────────────────────────────────
# Una sola instancia de timer activa en todo momento. El bloqueo (Lock) protege
# el acceso concurrente desde el hilo del Timer y el hilo principal de Tk.

_timer: Optional[threading.Timer] = None
_timer_lock: threading.Lock = threading.Lock()


# ── API pública ───────────────────────────────────────────────────────────────


def copy_to_clipboard(root: tk.Tk, value: str, clear_after_s: int = 20) -> None:
    """Copia *value* al portapapeles e inicia el timer de borrado automático.

    Cancela cualquier timer previo antes de establecer el nuevo valor, de modo
    que solo existe un timer activo en todo momento.

    Args:
        root:          Ventana raíz Tk (necesaria para acceder al portapapeles
                       y para despachar el borrado al hilo principal).
        value:         Texto a copiar (usuario o contraseña).
        clear_after_s: Segundos hasta el borrado automático.
                       0 desactiva el borrado automático (C-004 edge case).

    Refs: FR-015 (copiar al portapapeles), FR-016 (borrado tras timeout),
          US5 Acceptance Scenarios 1–2.
    """
    _cancel_timer()
    root.clipboard_clear()
    root.clipboard_append(value)

    if clear_after_s > 0:
        _start_timer(root, clear_after_s)


def cancel_clipboard_timer(root: tk.Tk) -> None:
    """Cancela el timer pendiente y limpia el portapapeles inmediatamente.

    Debe llamarse al bloquear la bóveda (manual o auto-bloqueo).

    Args:
        root: Ventana raíz Tk.

    Refs: FR-022 (borrado inmediato al bloquear), US5 Acceptance Scenario 3.
    """
    _cancel_timer()
    root.clipboard_clear()


# ── Helpers internos ──────────────────────────────────────────────────────────


def _start_timer(root: tk.Tk, delay_s: int) -> None:
    """Crea e inicia un nuevo Timer que borrará el portapapeles tras delay_s."""
    global _timer
    with _timer_lock:
        t = threading.Timer(delay_s, _do_clear, args=[root])
        t.daemon = True
        t.start()
        _timer = t


def _cancel_timer() -> None:
    """Cancela el timer activo si existe, sin tocar el portapapeles."""
    global _timer
    with _timer_lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None


def _do_clear(root: tk.Tk) -> None:
    """Callback del Timer — despacha el borrado al hilo principal de Tk.

    threading.Timer se ejecuta en un hilo auxiliar; Tkinter NO es thread-safe,
    por lo que usamos root.after(0, ...) para transferir la operación al hilo
    principal del event loop de Tk.

    Refs: FR-016 (borrado automático), SC-005 (dentro del timeout).
    """
    root.after(0, root.clipboard_clear)
