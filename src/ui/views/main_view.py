"""Vista principal — lista de entradas y operaciones CRUD (T022).

Responsabilidades:
  - Mostrar lista de entradas en un Treeview (columnas: Título, Usuario).
  - Botón "Nueva entrada" → abre EntryFormView en modo creación (US2 Sc1).
  - Doble clic en entrada → abre EntryFormView en modo edición (US2 Sc2).
  - Botón "Eliminar" → confirmación con askyesno → elimina (US2 Sc3–4).
  - Refresca la lista tras cada operación CRUD.

Constitución: Principio VII — confirmación antes de eliminar (FR-012).
Refs: spec.md → US2 Acceptance Scenarios 1–4; data-model.md → EntryRecord.
"""
import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Optional

from vault.exceptions import EntryNotFoundError

if TYPE_CHECKING:
    from ui.app import App
    from vault.models import EntryRecord

# Columnas del Treeview
_COL_TITLE = "title"
_COL_USER = "username"


class MainView(tk.Frame):
    """Vista principal de la bóveda desbloqueada con lista de entradas."""

    def __init__(self, parent: tk.Widget, app: "App") -> None:
        super().__init__(parent, padx=16, pady=12)
        self._app = app
        self._build_ui()
        self._refresh_entries()

    # ── Construcción de la UI ─────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Barra de acciones ─────────────────────────────────────────────────
        action_bar = tk.Frame(self)
        action_bar.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            action_bar,
            text="Entradas de credenciales",
            font=("", 13, "bold"),
        ).pack(side=tk.LEFT)

        tk.Button(
            action_bar,
            text="+ Nueva entrada",
            command=self._open_create_form,
            cursor="hand2",
            bg="#27ae60",
            fg="white",
            relief="flat",
            padx=8,
        ).pack(side=tk.RIGHT, padx=(4, 0))

        self._delete_btn = tk.Button(
            action_bar,
            text="🗑 Eliminar",
            command=self._delete_selected,
            cursor="hand2",
            bg="#c0392b",
            fg="white",
            relief="flat",
            padx=8,
            state=tk.DISABLED,
        )
        self._delete_btn.pack(side=tk.RIGHT, padx=(4, 0))

        # ── Treeview ──────────────────────────────────────────────────────────
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree = ttk.Treeview(
            tree_frame,
            columns=(_COL_TITLE, _COL_USER),
            show="headings",
            selectmode="browse",
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self._tree.yview)

        self._tree.heading(_COL_TITLE, text="Título")
        self._tree.heading(_COL_USER, text="Usuario")
        self._tree.column(_COL_TITLE, width=260, anchor="w")
        self._tree.column(_COL_USER, width=180, anchor="w")
        self._tree.pack(fill=tk.BOTH, expand=True)

        # ── Label estado vacío ────────────────────────────────────────────────
        self._empty_label = tk.Label(
            self,
            text="No hay entradas. Usa '+ Nueva entrada' para añadir la primera.",
            fg="gray",
        )

        # ── Eventos ───────────────────────────────────────────────────────────
        self._tree.bind("<<TreeviewSelect>>", self._on_selection_change)
        self._tree.bind("<Double-1>", self._on_double_click)

    # ── Datos ─────────────────────────────────────────────────────────────────

    def _refresh_entries(self) -> None:
        """Recarga la lista de entradas desde VaultService y actualiza el Treeview."""
        for iid in self._tree.get_children():
            self._tree.delete(iid)

        try:
            entries: list["EntryRecord"] = self._app.service.get_entries()
        except Exception:
            entries = []

        for entry in entries:
            self._tree.insert(
                "",
                tk.END,
                iid=entry.id,
                values=(entry.title, entry.username),
            )

        if entries:
            self._empty_label.pack_forget()
        else:
            self._empty_label.pack(pady=8)

        # Actualizar estado del botón Eliminar
        self._update_delete_btn()

    def _selected_entry_id(self) -> Optional[str]:
        """Devuelve el ID de la entrada seleccionada, o None."""
        sel = self._tree.selection()
        return sel[0] if sel else None

    # ── Acciones ─────────────────────────────────────────────────────────────

    def _open_create_form(self) -> None:
        """Abre EntryFormView en modo creación (US2 Acceptance Scenario 1)."""
        from ui.views.entry_form_view import EntryFormView
        EntryFormView(self, self._app, entry=None, on_saved=self._refresh_entries)

    def _open_edit_form(self, entry: "EntryRecord") -> None:
        """Abre EntryFormView en modo edición (US2 Acceptance Scenario 2)."""
        from ui.views.entry_form_view import EntryFormView
        EntryFormView(self, self._app, entry=entry, on_saved=self._refresh_entries)

    def _delete_selected(self) -> None:
        """Elimina la entrada seleccionada tras confirmación del usuario.

        Ref: spec.md → US2 Sc3 (eliminar con confirmación) y Sc4 (cancelar = no eliminar).
        Constitución: Principio VII — confirmación explícita para acciones destructivas (FR-012).
        """
        entry_id = self._selected_entry_id()
        if not entry_id:
            return

        # Obtener título para el mensaje de confirmación
        values = self._tree.item(entry_id, "values")
        title_text = values[0] if values else entry_id

        confirmed = messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Eliminar la entrada «{title_text}»?\n\nEsta acción no se puede deshacer.",
            icon="warning",
            parent=self,
        )
        if not confirmed:
            # US2 Sc4: usuario cancela → no se elimina
            return

        try:
            self._app.service.delete_entry(entry_id)
        except EntryNotFoundError:
            messagebox.showerror(
                "Error",
                "La entrada ya no existe en la bóveda.",
                parent=self,
            )
        self._refresh_entries()

    # ── Eventos ───────────────────────────────────────────────────────────────

    def _on_selection_change(self, _event: tk.Event) -> None:
        self._update_delete_btn()

    def _on_double_click(self, event: tk.Event) -> None:
        """Doble clic en una fila abre el formulario de edición."""
        region = self._tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        entry_id = self._selected_entry_id()
        if not entry_id:
            return
        entries = self._app.service.get_entries()
        entry = next((e for e in entries if e.id == entry_id), None)
        if entry:
            self._open_edit_form(entry)

    def _update_delete_btn(self) -> None:
        has_selection = bool(self._tree.selection())
        self._delete_btn.config(state=tk.NORMAL if has_selection else tk.DISABLED)

