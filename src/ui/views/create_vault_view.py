"""Vista de creación de nueva bóveda (T015).

Responsabilidades:
  - Seleccionar ruta del archivo.
  - Ingresar y confirmar contraseña maestra.
  - Mostrar advertencia obligatoria (FR-020).
  - Requerir confirmación explícita antes de habilitar "Crear".
  - Llamar a VaultService.create_vault().

Constitución: Principio VII — UX consistente en español (C-006).
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.app import App

_WARNING_TEXT = (
    "⚠  ADVERTENCIA IMPORTANTE\n\n"
    "La contraseña maestra NO puede recuperarse si la olvida.\n"
    "No existe ningún mecanismo de recuperación.\n"
    "Si pierde su contraseña, perderá acceso permanente a todos sus datos.\n\n"
    "Guarde su contraseña en un lugar seguro antes de continuar."
)


class CreateVaultView(tk.Frame):
    """Formulario para crear una nueva bóveda."""

    def __init__(self, parent: tk.Widget, app: "App") -> None:
        super().__init__(parent, padx=20, pady=20)
        self._app = app
        self._vault_path: Path | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        # ── Título ──────────────────────────────────────────────────────────
        tk.Label(
            self,
            text="Crear nueva bóveda",
            font=("", 16, "bold"),
        ).grid(row=0, column=0, columnspan=3, pady=(0, 16), sticky="w")

        # ── Ruta del archivo ─────────────────────────────────────────────────
        tk.Label(self, text="Ubicación del archivo:").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self._path_var = tk.StringVar()
        tk.Entry(self, textvariable=self._path_var, width=40, state="readonly").grid(
            row=1, column=1, padx=(8, 4), pady=4
        )
        tk.Button(self, text="Examinar…", command=self._browse).grid(
            row=1, column=2, pady=4
        )

        # ── Contraseña maestra ───────────────────────────────────────────────
        tk.Label(self, text="Contraseña maestra:").grid(
            row=2, column=0, sticky="w", pady=4
        )
        self._password_var = tk.StringVar()
        tk.Entry(self, textvariable=self._password_var, show="•", width=40).grid(
            row=2, column=1, columnspan=2, padx=(8, 0), pady=4
        )

        tk.Label(self, text="Confirmar contraseña:").grid(
            row=3, column=0, sticky="w", pady=4
        )
        self._confirm_var = tk.StringVar()
        tk.Entry(self, textvariable=self._confirm_var, show="•", width=40).grid(
            row=3, column=1, columnspan=2, padx=(8, 0), pady=4
        )

        # ── Advertencia obligatoria (FR-020) ─────────────────────────────────
        warning_frame = tk.Frame(self, bg="#fff3cd", bd=1, relief="solid")
        warning_frame.grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=(16, 8)
        )
        tk.Label(
            warning_frame,
            text=_WARNING_TEXT,
            bg="#fff3cd",
            fg="#856404",
            justify="left",
            wraplength=460,
            padx=12,
            pady=8,
        ).pack(anchor="w")

        # ── Checkbox de confirmación ─────────────────────────────────────────
        self._confirmed_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self,
            text="Entiendo que no podré recuperar mi contraseña maestra",
            variable=self._confirmed_var,
            command=self._on_confirm_toggle,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 12))

        # ── Etiqueta de error ────────────────────────────────────────────────
        self._error_var = tk.StringVar()
        self._error_label = tk.Label(
            self, textvariable=self._error_var, fg="red", wraplength=460
        )
        self._error_label.grid(row=6, column=0, columnspan=3, sticky="w")

        # ── Botones ──────────────────────────────────────────────────────────
        btn_frame = tk.Frame(self)
        btn_frame.grid(row=7, column=0, columnspan=3, sticky="e", pady=(8, 0))

        tk.Button(btn_frame, text="Cancelar", command=self._cancel).pack(
            side="right", padx=(8, 0)
        )
        self._create_btn = tk.Button(
            btn_frame,
            text="Crear bóveda",
            command=self._create,
            state="disabled",
        )
        self._create_btn.pack(side="right")

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _browse(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Elegir ubicación de la bóveda",
            defaultextension=".vault",
            filetypes=[("Archivos de bóveda", "*.vault"), ("Todos", "*.*")],
        )
        if path:
            self._vault_path = Path(path)
            self._path_var.set(path)

    def _on_confirm_toggle(self) -> None:
        if self._confirmed_var.get():
            self._create_btn.config(state="normal")
        else:
            self._create_btn.config(state="disabled")

    def _create(self) -> None:
        self._error_var.set("")

        if self._vault_path is None:
            self._error_var.set("Seleccione la ubicación del archivo.")
            return

        password = self._password_var.get()
        confirm = self._confirm_var.get()

        if not password:
            self._error_var.set("La contraseña maestra no puede estar vacía.")
            return

        if password != confirm:
            self._error_var.set("Las contraseñas no coinciden.")
            self._confirm_var.set("")
            return

        try:
            self._app.service.create_vault(self._vault_path, password)
        except Exception as exc:
            self._error_var.set(str(exc))
            return

        # Navegar a la vista principal
        from ui.views.main_view import MainView
        self._app.show_view(MainView)

    def _cancel(self) -> None:
        from ui.views.unlock_view import UnlockView
        self._app.show_view(UnlockView)
