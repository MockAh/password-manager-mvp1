"""Vista principal — lista de entradas, búsqueda en tiempo real y CRUD (T022, T025, T030, T033).

Responsabilidades:
  - Mostrar lista de entradas en un Treeview (columnas: Título, Usuario).
  - Barra de búsqueda en tiempo real — filtra por título o usuario (US3).
  - Panel lateral de carpetas con Listbox: "Todas las entradas", "Sin carpeta", carpetas (US6).
  - Botón "Nueva carpeta" (simpledialog.askstring) y "Eliminar carpeta" con confirmación (US6).
  - Seleccionar carpeta filtra la lista de entradas (US6 Sc3).
  - Botón "Nueva entrada" → abre EntryFormView en modo creación (US2 Sc1).
  - Doble clic en entrada → abre EntryFormView en modo edición (US2 Sc2).
  - Botón "Eliminar" → confirmación con askyesno → elimina (US2 Sc3–4).
  - Botones "Copiar usuario" y "Copiar contraseña" para la entrada seleccionada (US5).
  - Confirmación visual transitoria (≤ 2 s) tras copiar.
  - Refresca la lista tras cada operación CRUD.

Constitución: Principio VII — confirmación antes de eliminar (FR-012).
Refs: spec.md → US2 Acceptance Scenarios 1–4; US3 Acceptance Scenarios 1–3;
               US5 Acceptance Scenarios 1–3; US6 Acceptance Scenarios 1–4.
       FR-013 (búsqueda), FR-014 (carpetas), FR-015 (copiar),
       FR-022 (borrado inmediato al bloquear).
       SC-003 (≤ 100 ms / 500 entradas).
       Clarificación C-003 (eliminar carpeta mueve entradas a "Sin carpeta").
       data-model.md → EntryRecord, FolderRecord.
"""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import TYPE_CHECKING, Optional

from vault.exceptions import DuplicateFolderNameError, EntryNotFoundError, FolderNotFoundError

if TYPE_CHECKING:
    from ui.app import App
    from vault.models import EntryRecord

# Columnas del Treeview
_COL_TITLE = "title"
_COL_USER = "username"

# Sentineles para el panel de carpetas
_ALL_ENTRIES_LABEL = "Todas las entradas"
_NO_FOLDER_LABEL = "Sin carpeta"


class MainView(tk.Frame):
    """Vista principal de la bóveda desbloqueada con lista de entradas y panel de carpetas."""

    def __init__(self, parent: tk.Widget, app: "App") -> None:
        super().__init__(parent, padx=16, pady=12)
        self._app = app
        # _active_folder: None → todas; "" (NO_FOLDER) → sin carpeta; uuid → carpeta concreta
        self._active_folder_id: Optional[str] = None
        self._folders: list = []  # cache de FolderRecord para el panel lateral
        self._build_ui()
        self._refresh_folders()
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

        # Botones copiar (US5, FR-015) — habilitados cuando hay selección
        self._copy_pwd_btn = tk.Button(
            action_bar,
            text="🔑 Copiar contraseña",
            command=self._copy_password,
            cursor="hand2",
            relief="flat",
            padx=8,
            state=tk.DISABLED,
        )
        self._copy_pwd_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self._copy_user_btn = tk.Button(
            action_bar,
            text="👤 Copiar usuario",
            command=self._copy_user,
            cursor="hand2",
            relief="flat",
            padx=8,
            state=tk.DISABLED,
        )
        self._copy_user_btn.pack(side=tk.RIGHT, padx=(4, 0))

        # ── Barra de búsqueda (US3, FR-013) ───────────────────────────────────
        search_bar = tk.Frame(self)
        search_bar.pack(fill=tk.X, pady=(0, 4))

        tk.Label(search_bar, text="Buscar:").pack(side=tk.LEFT, padx=(0, 6))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_changed)
        tk.Entry(
            search_bar,
            textvariable=self._search_var,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Layout principal: panel lateral (carpetas) + panel derecho (entradas)
        main_pane = tk.Frame(self)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # ── Panel lateral de carpetas (US6, FR-014) ───────────────────────────
        folder_panel = tk.Frame(main_pane, width=160, relief="groove", bd=1)
        folder_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        folder_panel.pack_propagate(False)

        tk.Label(
            folder_panel,
            text="Carpetas",
            font=("", 10, "bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=6, pady=(6, 2))

        folder_list_frame = tk.Frame(folder_panel)
        folder_list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        folder_scroll = ttk.Scrollbar(folder_list_frame, orient=tk.VERTICAL)
        folder_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._folder_listbox = tk.Listbox(
            folder_list_frame,
            yscrollcommand=folder_scroll.set,
            selectmode=tk.SINGLE,
            activestyle="none",
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        folder_scroll.config(command=self._folder_listbox.yview)
        self._folder_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._folder_listbox.bind("<<ListboxSelect>>", self._on_folder_selected)

        # Botones de gestión de carpetas
        folder_btn_bar = tk.Frame(folder_panel)
        folder_btn_bar.pack(fill=tk.X, padx=4, pady=(0, 6))

        tk.Button(
            folder_btn_bar,
            text="+ Carpeta",
            command=self._add_folder,
            cursor="hand2",
            relief="flat",
            bg="#2980b9",
            fg="white",
            padx=4,
            font=("", 8),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        self._del_folder_btn = tk.Button(
            folder_btn_bar,
            text="🗑",
            command=self._delete_folder,
            cursor="hand2",
            relief="flat",
            bg="#c0392b",
            fg="white",
            padx=4,
            font=("", 8),
            state=tk.DISABLED,
        )
        self._del_folder_btn.pack(side=tk.LEFT)

        # ── Panel derecho: Treeview de entradas ───────────────────────────────
        right_panel = tk.Frame(main_pane)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tree_frame = tk.Frame(right_panel)
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

        # ── Labels de estado ────────────────────────────────────────────────
        self._empty_label = tk.Label(
            right_panel,
            text="No hay entradas. Usa '+ Nueva entrada' para añadir la primera.",
            fg="gray",
        )
        # Mostrado cuando la búsqueda activa no produce resultados (US3 Sc3).
        self._no_results_label = tk.Label(
            right_panel,
            text="Sin resultados.",
            fg="gray",
        )

        # Confirmación visual transitoria tras copiar al portapapeles (US5 Sc1).
        self._copy_toast = tk.Label(
            right_panel,
            text="",
            fg="#27ae60",
            font=("" , 9),
        )

        # ── Eventos ───────────────────────────────────────────────────────────
        self._tree.bind("<<TreeviewSelect>>", self._on_selection_change)
        self._tree.bind("<Double-1>", self._on_double_click)

    # ── Datos ─────────────────────────────────────────────────────────────────

    def _refresh_folders(self) -> None:
        """Recarga la lista de carpetas y actualiza el Listbox lateral.

        Restablece la selección al ítem activo actual (o a "Todas las entradas"
        si la carpeta activa ya no existe).

        Refs: FR-014 (listar carpetas), US6 Acceptance Scenario 3.
        """
        try:
            self._folders = self._app.service.get_folders()
        except Exception:
            self._folders = []

        lb = self._folder_listbox
        lb.delete(0, tk.END)
        lb.insert(tk.END, _ALL_ENTRIES_LABEL)
        lb.insert(tk.END, _NO_FOLDER_LABEL)
        for folder in self._folders:
            lb.insert(tk.END, folder.name)

        # Restaurar selección visual
        active = self._active_folder_id
        if active is None:
            lb.selection_set(0)           # "Todas las entradas"
        elif active == "":
            lb.selection_set(1)           # "Sin carpeta"
        else:
            folder_names = [f.name for f in self._folders]
            folder_ids = [f.id for f in self._folders]
            if active in folder_ids:
                idx = folder_ids.index(active) + 2
                lb.selection_set(idx)
            else:
                # Carpeta ya no existe — resetear a "Todas las entradas"
                self._active_folder_id = None
                lb.selection_set(0)

        self._update_del_folder_btn()

    def _refresh_entries(self) -> None:
        """Recarga la lista de entradas desde VaultService y actualiza el Treeview.

        Respeta el filtro activo de carpeta (_active_folder_id) y la búsqueda:
          - Si hay query activo, delega en search_entries() dentro del subconjunto
            de la carpeta (filtrado en cliente — SC-003).
          - Si no hay query, usa get_entries(folder_id=_active_folder_id).

        Refs: FR-013 (búsqueda en tiempo real), FR-014 (filtro de carpeta),
              US3 Acceptance Scenarios 1–3, US6 Acceptance Scenario 3,
              SC-003 (≤ 100 ms / 500 entradas).
        """
        for iid in self._tree.get_children():
            self._tree.delete(iid)

        query = self._search_var.get().strip()
        try:
            if query:
                # US3: filtrar por query; luego aplicar filtro de carpeta en cliente.
                all_matches: list["EntryRecord"] = self._app.service.search_entries(query)
                active = self._active_folder_id
                if active is None:
                    entries = all_matches
                elif active == "":
                    from vault.service import NO_FOLDER as _NF
                    entries = [e for e in all_matches if e.folder_id is None]
                else:
                    entries = [e for e in all_matches if e.folder_id == active]
            else:
                # US6 Sc3: filtrar por carpeta activa.
                entries = self._app.service.get_entries(folder_id=self._active_folder_id)
        except Exception:
            entries = []

        for entry in entries:
            self._tree.insert(
                "",
                tk.END,
                iid=entry.id,
                values=(entry.title, entry.username),
            )

        # Gestionar labels de estado
        self._empty_label.pack_forget()
        self._no_results_label.pack_forget()

        if not entries:
            if query:
                self._no_results_label.pack(pady=8)
            else:
                self._empty_label.pack(pady=8)

        self._update_action_btns()

    def _selected_entry_id(self) -> Optional[str]:
        """Devuelve el ID de la entrada seleccionada, o None."""
        sel = self._tree.selection()
        return sel[0] if sel else None

    def _get_selected_entry(self) -> Optional["EntryRecord"]:
        """Devuelve el EntryRecord completo de la fila seleccionada, o None."""
        entry_id = self._selected_entry_id()
        if not entry_id:
            return None
        try:
            return next(
                (e for e in self._app.service.get_entries() if e.id == entry_id),
                None,
            )
        except Exception:
            return None

    def _get_active_folder_id_for_new_entry(self) -> Optional[str]:
        """Devuelve el folder_id a preseleccionar para una nueva entrada.

        Si la vista activa es una carpeta concreta, devuelve su UUID.
        En caso contrario devuelve None (sin carpeta preseleccionada).

        Ref: T034 — preseleccionar carpeta activa al abrir formulario desde carpeta.
        """
        active = self._active_folder_id
        if active and active != "":
            return active
        return None

    # ── Acciones de carpeta (US6) ─────────────────────────────────────────────

    def _add_folder(self) -> None:
        """Abre un diálogo para crear una nueva carpeta.

        Refs: FR-014 (crear carpeta), US6 Acceptance Scenario 1.
        """
        name = simpledialog.askstring(
            "Nueva carpeta",
            "Nombre de la carpeta:",
            parent=self,
        )
        if not name:
            return
        try:
            self._app.service.add_folder(name)
        except DuplicateFolderNameError:
            messagebox.showerror(
                "Nombre duplicado",
                f"Ya existe una carpeta con el nombre «{name}».",
                parent=self,
            )
            return
        except ValueError as exc:
            messagebox.showerror("Nombre inválido", str(exc), parent=self)
            return
        self._refresh_folders()
        self._refresh_entries()

    def _delete_folder(self) -> None:
        """Elimina la carpeta seleccionada tras confirmación del usuario.

        Informa cuántas entradas pasarán a «Sin carpeta» (C-003).

        Refs: US6 Acceptance Scenario 4; C-003; Principio VII (confirmación).
        """
        active = self._active_folder_id
        if not active or active == "":
            return
        folder_name = next(
            (f.name for f in self._folders if f.id == active), active
        )
        # Contar entradas afectadas para informar al usuario (US6 Sc4)
        try:
            affected = len(self._app.service.get_entries(folder_id=active))
        except Exception:
            affected = 0

        if affected > 0:
            msg = (
                f"¿Eliminar la carpeta «{folder_name}»?\n\n"
                f"{affected} entrada(s) pasarán a «Sin carpeta».\n"
                "Esta acción no se puede deshacer."
            )
        else:
            msg = (
                f"¿Eliminar la carpeta «{folder_name}»?\n\n"
                "La carpeta está vacía. Esta acción no se puede deshacer."
            )

        confirmed = messagebox.askyesno(
            "Confirmar eliminación de carpeta",
            msg,
            icon="warning",
            parent=self,
        )
        if not confirmed:
            return

        try:
            self._app.service.delete_folder(active)
        except FolderNotFoundError:
            messagebox.showerror(
                "Error",
                "La carpeta ya no existe.",
                parent=self,
            )
        # Volver a "Todas las entradas" tras eliminar la carpeta activa
        self._active_folder_id = None
        self._refresh_folders()
        self._refresh_entries()

    def _update_del_folder_btn(self) -> None:
        """Habilita el botón eliminar carpeta solo cuando hay una carpeta real seleccionada."""
        active = self._active_folder_id
        can_delete = active is not None and active != ""
        self._del_folder_btn.config(
            state=tk.NORMAL if can_delete else tk.DISABLED
        )

    # ── Acciones ─────────────────────────────────────────────────────────────

    def _copy_user(self) -> None:
        """Copia el usuario de la entrada seleccionada al portapapeles.

        Refs: FR-015 (copiar al portapapeles), US5 Acceptance Scenario 1.
        """
        entry = self._get_selected_entry()
        if entry is None:
            return
        from ui import clipboard
        clipboard.copy_to_clipboard(self._app.root, entry.username)
        self._show_copy_toast("✓ Usuario copiado")

    def _copy_password(self) -> None:
        """Copia la contraseña de la entrada seleccionada al portapapeles.

        Refs: FR-015 (copiar al portapapeles), US5 Acceptance Scenario 1.
        """
        entry = self._get_selected_entry()
        if entry is None:
            return
        from ui import clipboard
        clipboard.copy_to_clipboard(self._app.root, entry.password)
        self._show_copy_toast("✓ Contraseña copiada")

    def _show_copy_toast(self, message: str) -> None:
        """Muestra confirmación visual transitoria que desaparece tras 2 s.

        Ref: US5 Acceptance Scenario 1 — confirmación visual tras copiar.
        """
        self._copy_toast.config(text=message)
        self._copy_toast.pack(pady=(2, 0))
        self._app.root.after(2000, self._copy_toast.pack_forget)

    def _open_create_form(self) -> None:
        """Abre EntryFormView en modo creación (US2 Acceptance Scenario 1).

        Pre-selecciona la carpeta activa si el usuario está dentro de una (T034).
        Ref: US6 — al crear desde una carpeta, la nueva entrada se asigna a ella.
        """
        from ui.views.entry_form_view import EntryFormView
        active_folder_id = self._get_active_folder_id_for_new_entry()
        EntryFormView(
            self, self._app, entry=None,
            on_saved=self._on_entry_saved,
            active_folder_id=active_folder_id,
        )

    def _open_edit_form(self, entry: "EntryRecord") -> None:
        """Abre EntryFormView en modo edición (US2 Acceptance Scenario 2)."""
        from ui.views.entry_form_view import EntryFormView
        EntryFormView(self, self._app, entry=entry, on_saved=self._on_entry_saved)

    def _on_entry_saved(self) -> None:
        """Callback tras guardar una entrada — refresca carpetas y entradas."""
        self._refresh_folders()
        self._refresh_entries()

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

    def _on_folder_selected(self, _event: tk.Event) -> None:
        """Actualiza el filtro de carpeta activa y refresca la lista de entradas.

        Refs: US6 Acceptance Scenario 3 — seleccionar carpeta filtra la lista.
        """
        sel = self._folder_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == 0:
            self._active_folder_id = None          # "Todas las entradas"
        elif idx == 1:
            self._active_folder_id = ""             # "Sin carpeta" (NO_FOLDER)
        else:
            folder_idx = idx - 2
            if folder_idx < len(self._folders):
                self._active_folder_id = self._folders[folder_idx].id
        self._update_del_folder_btn()
        self._refresh_entries()

    def _on_search_changed(self, *_args) -> None:
        """Callback disparado por StringVar en cada pulsación de tecla.

        Llama a search_entries(query) si hay texto, get_entries() si está vacío,
        y actualiza el Treeview inmediatamente.

        Refs: T025 (US3), FR-013, US3 Acceptance Scenario 1.
        """
        self._refresh_entries()

    def _on_selection_change(self, _event: tk.Event) -> None:
        self._update_action_btns()

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

    def _update_action_btns(self) -> None:
        """Habilita o deshabilita botones que requieren una fila seleccionada."""
        state = tk.NORMAL if self._tree.selection() else tk.DISABLED
        self._delete_btn.config(state=state)
        self._copy_user_btn.config(state=state)
        self._copy_pwd_btn.config(state=state)

