"""Vista principal — stub de Fase 3 (T017 dependencia).

Placeholder para US2–US7 (implementadas en Fases 4-9).
Muestra estado desbloqueado y ofrece el botón de bloqueo.
"""
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.app import App


class MainView(tk.Frame):
    """Vista del contenido de la bóveda (stub para Fase 3)."""

    def __init__(self, parent: tk.Widget, app: "App") -> None:
        super().__init__(parent, padx=20, pady=20)
        self._app = app
        self._build_ui()

    def _build_ui(self) -> None:
        tk.Label(
            self,
            text="Bóveda desbloqueada",
            font=("", 14, "bold"),
            fg="green",
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            self,
            text="Lista de credenciales — próximamente (US2–US3).",
            fg="gray",
        ).pack(anchor="w")

        # Placeholder para la lista de entradas (Fase 4)
        self._list_frame = tk.Frame(self, bg="#f5f5f5", height=300)
        self._list_frame.pack(fill="both", expand=True, pady=16)
        self._list_frame.pack_propagate(False)
        tk.Label(
            self._list_frame,
            text="(sin entradas)",
            fg="gray",
            bg="#f5f5f5",
        ).pack(expand=True)
