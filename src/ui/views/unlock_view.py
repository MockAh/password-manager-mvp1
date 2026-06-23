"""Vista de desbloqueo de bóveda (T016).

Responsabilidades:
  - Seleccionar o mostrar la ruta del archivo de bóveda.
  - Ingresar contraseña maestra.
  - Llamar a VaultService.unlock_vault() y mostrar errores.
  - Enlace para crear una nueva bóveda.
  - Tecla <Return> para desbloquear.

Constitución: Principio VII — UX consistente en español (C-006).
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.app import App


class UnlockView(tk.Frame):
    """Formulario de inicio de sesión — desbloquear bóveda existente."""

    def __init__(self, parent: tk.Widget, app: "App") -> None:
        super().__init__(parent, padx=30, pady=30)
        self._app = app
        self._vault_path: Path | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        # ── Título ───────────────────────────────────────────────────────────
        tk.Label(
            self,
            text="Gestor de Contraseñas",
            font=("", 18, "bold"),
        ).grid(row=0, column=0, columnspan=3, pady=(0, 4), sticky="w")

        tk.Label(
            self,
            text="Desbloquee su bóveda para continuar.",
            fg="gray",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 20))

        # ── Selección del archivo ────────────────────────────────────────────
        tk.Label(self, text="Archivo de bóveda:").grid(
            row=2, column=0, sticky="w", pady=4
        )
        self._path_var = tk.StringVar()
        tk.Entry(self, textvariable=self._path_var, width=38, state="readonly").grid(
            row=2, column=1, padx=(8, 4), pady=4
        )
        tk.Button(self, text="Examinar…", command=self._browse).grid(
            row=2, column=2, pady=4
        )

        # ── Contraseña maestra ───────────────────────────────────────────────
        tk.Label(self, text="Contraseña maestra:").grid(
            row=3, column=0, sticky="w", pady=4
        )
        self._password_var = tk.StringVar()
        self._password_entry = tk.Entry(
            self, textvariable=self._password_var, show="•", width=38
        )
        self._password_entry.grid(row=3, column=1, columnspan=2, padx=(8, 0), pady=4)
        self._password_entry.bind("<Return>", lambda _: self._unlock())
        self._password_entry.focus()

        # ── Mensaje de error ─────────────────────────────────────────────────
        self._error_var = tk.StringVar()
        tk.Label(
            self,
            textvariable=self._error_var,
            fg="red",
            wraplength=380,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # ── Botón principal ──────────────────────────────────────────────────
        tk.Button(
            self,
            text="Desbloquear",
            command=self._unlock,
            width=18,
        ).grid(row=5, column=0, columnspan=3, pady=(16, 8))

        # ── Enlace para crear bóveda ─────────────────────────────────────────
        create_link = tk.Label(
            self,
            text="Crear nueva bóveda",
            fg="#0066cc",
            cursor="hand2",
        )
        create_link.grid(row=6, column=0, columnspan=3)
        create_link.bind("<Button-1>", lambda _: self._go_to_create())

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Abrir bóveda",
            filetypes=[("Archivos de bóveda", "*.vault"), ("Todos", "*.*")],
        )
        if path:
            self._vault_path = Path(path)
            self._path_var.set(path)

    def _unlock(self) -> None:
        self._error_var.set("")

        if self._vault_path is None:
            self._error_var.set("Seleccione el archivo de bóveda.")
            return

        password = self._password_var.get()
        if not password:
            self._error_var.set("Introduzca la contraseña maestra.")
            return

        try:
            self._app.service.unlock_vault(self._vault_path, password)
        except Exception as exc:
            self._error_var.set(str(exc))
            self._password_var.set("")
            self._password_entry.focus()
            return

        from ui.views.main_view import MainView
        self._app.show_view(MainView)

    def _go_to_create(self) -> None:
        from ui.views.create_vault_view import CreateVaultView
        self._app.show_view(CreateVaultView)
