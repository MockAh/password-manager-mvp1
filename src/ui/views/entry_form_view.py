"""Formulario de entrada — crear o editar una credencial (T021).

Responsabilidades:
  - Presentar campos de EntryRecord: title (obligatorio), username, password,
    url, notes, folder_id.
  - Modo creación: llama a VaultService.add_entry() al guardar.
  - Modo edición: llama a VaultService.update_entry() al guardar.
  - Validación de título no vacío con mensaje rojo.
  - Toggle de visibilidad de contraseña.
  - Selector de carpeta poblado con get_folders() (US6 preparado).

Constitución: Principio VII — confirmación explícita de acciones; mensajes en español.
Refs: spec.md → US2 Acceptance Scenarios 1–2; data-model.md → EntryRecord.
"""
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Callable, Optional

from vault.exceptions import FolderNotFoundError

if TYPE_CHECKING:
    from ui.app import App
    from vault.models import EntryRecord


class EntryFormView(tk.Toplevel):
    """Ventana de diálogo para crear o editar una entrada de credencial.

    Args:
        parent:      Widget padre (normalmente App o MainView).
        app:         Instancia de App (acceso a VaultService y navegación).
        entry:       EntryRecord a editar; None para modo creación.
        on_saved:    Callback llamado tras guardar exitosamente (para refrescar lista).
    """

    def __init__(
        self,
        parent: tk.Widget,
        app: "App",
        entry: Optional["EntryRecord"] = None,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._app = app
        self._entry = entry
        self._on_saved = on_saved
        self._password_visible = False

        title_text = "Editar entrada" if entry else "Nueva entrada"
        self.title(title_text)
        self.resizable(False, False)
        self.wait_visibility()
        self.grab_set()          # modal — bloquea la ventana padre
        self.focus_set()

        self._build_ui()
        if entry:
            self._populate(entry)

        # Centrar sobre la ventana raíz
        self.update_idletasks()
        rx = app.root.winfo_x() + (app.root.winfo_width() - self.winfo_width()) // 2
        ry = app.root.winfo_y() + (app.root.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{rx}+{ry}")

    # ── Construcción de la UI ─────────────────────────────────────────────────

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}
        container = tk.Frame(self, padx=16, pady=12)
        container.pack(fill=tk.BOTH, expand=True)

        # ── Título (obligatorio) ──────────────────────────────────────────────
        tk.Label(container, text="Título *", anchor="w").grid(
            row=0, column=0, sticky="w", **pad
        )
        self._title_var = tk.StringVar()
        self._title_entry = tk.Entry(container, textvariable=self._title_var, width=36)
        self._title_entry.grid(row=0, column=1, sticky="ew", **pad)

        self._title_error = tk.Label(
            container, text="El título no puede estar vacío.", fg="red", anchor="w"
        )
        # No visible hasta que el usuario intente guardar sin título

        # ── Usuario ───────────────────────────────────────────────────────────
        tk.Label(container, text="Usuario", anchor="w").grid(
            row=1, column=0, sticky="w", **pad
        )
        self._username_var = tk.StringVar()
        tk.Entry(container, textvariable=self._username_var, width=36).grid(
            row=1, column=1, sticky="ew", **pad
        )

        # ── Contraseña ────────────────────────────────────────────────────────
        tk.Label(container, text="Contraseña", anchor="w").grid(
            row=2, column=0, sticky="w", **pad
        )
        pwd_frame = tk.Frame(container)
        pwd_frame.grid(row=2, column=1, sticky="ew", **pad)

        self._password_var = tk.StringVar()
        self._password_entry = tk.Entry(
            pwd_frame, textvariable=self._password_var, show="*", width=28
        )
        self._password_entry.pack(side=tk.LEFT)

        self._eye_btn = tk.Button(
            pwd_frame,
            text="Mostrar",
            width=3,
            cursor="hand2",
            command=self._toggle_password_visibility,
            relief="flat",
        )
        self._eye_btn.pack(side=tk.LEFT, padx=(4, 0))

        # ── URL ───────────────────────────────────────────────────────────────
        tk.Label(container, text="URL", anchor="w").grid(
            row=3, column=0, sticky="w", **pad
        )
        self._url_var = tk.StringVar()
        tk.Entry(container, textvariable=self._url_var, width=36).grid(
            row=3, column=1, sticky="ew", **pad
        )

        # ── Notas ─────────────────────────────────────────────────────────────
        tk.Label(container, text="Notas", anchor="w").grid(
            row=4, column=0, sticky="nw", **pad
        )
        self._notes_text = tk.Text(container, width=36, height=5, wrap=tk.WORD)
        self._notes_text.grid(row=4, column=1, sticky="ew", **pad)

        # ── Carpeta ───────────────────────────────────────────────────────────
        tk.Label(container, text="Carpeta", anchor="w").grid(
            row=5, column=0, sticky="w", **pad
        )
        self._folder_options: list[tuple[str, Optional[str]]] = self._build_folder_options()
        folder_names = [label for label, _ in self._folder_options]
        self._folder_var = tk.StringVar(value=folder_names[0] if folder_names else "Sin carpeta")
        self._folder_menu = ttk.OptionMenu(
            container, self._folder_var, self._folder_var.get(), *folder_names
        )
        self._folder_menu.grid(row=5, column=1, sticky="w", **pad)

        container.columnconfigure(1, weight=1)

        # ── Botones ───────────────────────────────────────────────────────────
        btn_frame = tk.Frame(container)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=(12, 0), sticky="e")

        tk.Button(
            btn_frame,
            text="Cancelar",
            width=10,
            command=self.destroy,
            cursor="hand2",
        ).pack(side=tk.RIGHT, padx=(6, 0))

        tk.Button(
            btn_frame,
            text="Guardar",
            width=10,
            command=self._on_save,
            cursor="hand2",
            bg="#2980b9",
            fg="white",
            relief="flat",
        ).pack(side=tk.RIGHT)

    # ── Helpers de UI ────────────────────────────────────────────────────────

    def _toggle_password_visibility(self) -> None:
        self._password_visible = not self._password_visible
        self._password_entry.config(show="" if self._password_visible else "*")

    def _build_folder_options(self) -> list:
        """Construye lista de (etiqueta, folder_id | None) para el OptionMenu.

        'Sin carpeta' mapea a None. Cada carpeta usa su UUID como value.
        Ref: data-model.md → folder_id puede ser null.
        """
        options: list[tuple[str, Optional[str]]] = [("Sin carpeta", None)]
        try:
            for folder in self._app.service.get_folders():
                options.append((folder.name, folder.id))
        except Exception:
            pass  # bóveda aún no desbloqueada — ocurre solo en tests
        return options

    def _get_selected_folder_id(self) -> Optional[str]:
        label = self._folder_var.get()
        for name, fid in self._folder_options:
            if name == label:
                return fid
        return None

    def _populate(self, entry: "EntryRecord") -> None:
        """Rellena el formulario con los datos de una entrada existente."""
        self._title_var.set(entry.title)
        self._username_var.set(entry.username)
        self._password_var.set(entry.password)
        self._url_var.set(entry.url or "")
        self._notes_text.insert("1.0", entry.notes or "")
        # Preseleccionar carpeta
        for label, fid in self._folder_options:
            if fid == entry.folder_id:
                self._folder_var.set(label)
                break

    # ── Guardar ───────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        """Valida los campos y llama a add_entry o update_entry.

        Ref: spec.md → US2 Sc1 (crear) y Sc2 (editar).
        """
        title = self._title_var.get().strip()
        if not title:
            self._title_error.grid(row=0, column=1, sticky="w", padx=12)
            self._title_entry.focus_set()
            return
        self._title_error.grid_forget()

        username = self._username_var.get()
        password = self._password_var.get()
        url = self._url_var.get().strip()
        notes = self._notes_text.get("1.0", tk.END).rstrip("\n")
        folder_id = self._get_selected_folder_id()

        try:
            if self._entry is None:
                # Modo creación — US2 Acceptance Scenario 1
                self._app.service.add_entry(
                    title=title,
                    username=username,
                    password=password,
                    url=url,
                    notes=notes,
                    folder_id=folder_id,
                )
            else:
                # Modo edición — US2 Acceptance Scenario 2
                self._app.service.update_entry(
                    self._entry.id,
                    title=title,
                    username=username,
                    password=password,
                    url=url,
                    notes=notes,
                    folder_id=folder_id,
                )
        except FolderNotFoundError as exc:
            tk.messagebox.showerror("Error", str(exc), parent=self)
            return
        except Exception as exc:
            tk.messagebox.showerror("Error inesperado", str(exc), parent=self)
            return

        if self._on_saved:
            self._on_saved()
        self.destroy()
