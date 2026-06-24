"""Aplicación principal — contenedor de vistas y barra de herramientas (T017, T037, T039).

Responsabilidades:
  - Gestionar la navegación entre vistas (show_view).
  - Mostrar barra de herramientas con botón de bloqueo cuando la bóveda esté abierta.
  - Recibir el callback de auto-bloqueo desde VaultService y volver a UnlockView.
  - Registrar toda actividad del usuario (tecla, clic, scroll) para reiniciar el
    temporizador de inactividad (record_activity) — T037, US7 Sc3.
  - Cargar/guardar AppSettings y proporcionar el diálogo de Configuración — T039.

Constitución: Principio VII — UX consistente; Principio VIII — rendimiento UI.
"""
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import TYPE_CHECKING, Type

from vault.models import (
    APP_CONFIG_PATH,
    AppSettings,
    AUTO_LOCK_TIMEOUT_MAX,
    AUTO_LOCK_TIMEOUT_MIN,
    CLIPBOARD_TIMEOUT_MAX,
    CLIPBOARD_TIMEOUT_MIN,
    load_settings,
    save_settings,
)
from vault.service import VaultService

if TYPE_CHECKING:
    pass


class App(tk.Frame):
    """Frame raíz de la aplicación. Gestiona la navegación entre vistas."""

    def __init__(self, root: tk.Tk, service: VaultService) -> None:
        super().__init__(root)
        self.root = root
        self.service = service
        self._current_view: tk.Widget | None = None

        # Cargar configuración de usuario (T038/T039).
        # Usa ruta por defecto (~/.config/vault-manager/settings.json).
        self.settings: AppSettings = load_settings()
        # Aplicar timeout de auto-bloqueo leído de settings
        service.set_auto_lock_timeout(self.settings.auto_lock_timeout_s)

        self.pack(fill=tk.BOTH, expand=True)
        self._build_toolbar()

        self._view_container = tk.Frame(self)
        self._view_container.pack(fill=tk.BOTH, expand=True)

        # Mostrar vista inicial
        from ui.views.unlock_view import UnlockView
        self.show_view(UnlockView)

        # Inyectar callback de auto-bloqueo en el servicio
        service._on_auto_lock = self._on_auto_lock_callback

        # Registrar actividad del usuario para reiniciar el timer de inactividad.
        # Refs: FR-017, US7 Acceptance Scenario 3 — tecla, clic y scroll reinician el timer.
        self._register_activity_bindings()

    def _register_activity_bindings(self) -> None:
        """Registra listeners de actividad del usuario sobre toda la ventana.

        Cualquier pulsación de tecla, clic o scroll reinicia el temporizador
        de inactividad del servicio (record_activity).

        Refs: FR-017 (auto-bloqueo por inactividad), T037 (US7),
              US7 Acceptance Scenario 3 — «cualquier acción reinicia el temporizador».
        """
        self.root.bind_all("<KeyPress>", self._on_user_activity)
        self.root.bind_all("<ButtonPress>", self._on_user_activity)
        self.root.bind_all("<MouseWheel>", self._on_user_activity)

    def _on_user_activity(self, _event: tk.Event) -> None:
        """Callback disparado por cualquier evento de interacción del usuario.

        Delega en VaultService.record_activity() que, si la bóveda está
        desbloqueada, cancela y reinicia el timer de inactividad.

        Refs: FR-017, US7 Acceptance Scenario 3.
        """
        self.service.record_activity()

    def _build_toolbar(self) -> None:
        self._toolbar = tk.Frame(self, bg="#2d2d2d", pady=4)
        self._toolbar.pack(fill=tk.X, side=tk.TOP)

        tk.Label(
            self._toolbar,
            text="  🔐 Gestor de Contraseñas",
            bg="#2d2d2d",
            fg="white",
            font=("", 11, "bold"),
        ).pack(side=tk.LEFT, padx=4)

        # Botón de Configuración (T039) — siempre visible
        tk.Button(
            self._toolbar,
            text="⚙ Configuración",
            command=self._open_settings_dialog,
            bg="#555555",
            fg="white",
            relief="flat",
            cursor="hand2",
        ).pack(side=tk.RIGHT, padx=8)

        self._lock_btn = tk.Button(
            self._toolbar,
            text="🔒 Bloquear",
            command=self._lock_and_navigate,
            bg="#c0392b",
            fg="white",
            relief="flat",
            cursor="hand2",
        )
        # Oculto inicialmente; se muestra cuando la bóveda esté abierta
        self._lock_btn.pack_forget()

    def show_view(self, view_class: Type[tk.Frame], **kwargs) -> None:
        """Reemplaza la vista actual por una nueva instancia de view_class."""
        if self._current_view is not None:
            self._current_view.destroy()
            self._current_view = None

        self._current_view = view_class(self._view_container, self, **kwargs)
        self._current_view.pack(fill=tk.BOTH, expand=True)
        self._refresh_toolbar()

    def _refresh_toolbar(self) -> None:
        """Muestra u oculta el botón de bloqueo según el estado de la sesión."""
        if self.service.is_unlocked:
            self._lock_btn.pack(side=tk.RIGHT, padx=8)
        else:
            self._lock_btn.pack_forget()

    def _lock_and_navigate(self) -> None:
        """Bloquea la bóveda manualmente y navega a UnlockView.

        Limpia el portapapeles antes de bloquear (FR-022).
        Refs: US5 Acceptance Scenario 3 — portapapeles borrado al bloquear.
        """
        from ui import clipboard
        clipboard.cancel_clipboard_timer(self.root)
        self.service.lock_vault()
        from ui.views.unlock_view import UnlockView
        self.show_view(UnlockView)

    def _on_auto_lock_callback(self) -> None:
        """Llamado desde el hilo del Timer de VaultService al auto-bloquearse.

        Usa root.after para redirigir el cambio de UI al hilo principal de Tk.
        """
        self.root.after(0, self._navigate_to_unlock_after_autolock)

    def _navigate_to_unlock_after_autolock(self) -> None:
        """Callback del auto-bloqueo ejecutado en el hilo principal de Tk.

        Limpia el portapapeles antes de navegar (FR-022).
        Refs: US5 Acceptance Scenario 3 — portapapeles borrado al bloquear.
        """
        from ui import clipboard
        clipboard.cancel_clipboard_timer(self.root)
        from ui.views.unlock_view import UnlockView
        self.show_view(UnlockView)

    # ── Diálogo de Configuración (T039) ─────────────────────────────────────────

    def _open_settings_dialog(self) -> None:
        """Abre el diálogo modal de configuración de la aplicación.

        Refs: T039 (plan.md Phase 10); FR-016 (timeout portapapeles);
              FR-017 (timeout auto-bloqueo).
        """
        _SettingsDialog(self.root, self)


# ── Diálogo de Configuración (interno, T039) ──────────────────────────────────


class _SettingsDialog(tk.Toplevel):
    """Ventana modal de configuración de la aplicación.

    Permite al usuario ajustar:
      - Timeout de borrado del portapapeles (5–300 s) — FR-016, C-004.
      - Timeout de auto-bloqueo por inactividad (60–3600 s) — FR-017.

    Al guardar, persiste AppSettings en disco y actualiza VaultService.

    Refs: T039 (plan.md Phase 10).
    """

    def __init__(self, parent: tk.Tk, app: "App") -> None:
        super().__init__(parent)
        self.withdraw()          # ocultar hasta estar posicionada (Fix 1)
        self._app = app
        self.title("Configuración")
        self.resizable(False, False)

        self._build_ui()

        # Centrar sobre la ventana raíz antes de mostrar
        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

        self.deiconify()         # mostrar ya centrada (Fix 1)
        self.wait_visibility()
        self.grab_set()
        self.focus_set()

    def _build_ui(self) -> None:
        s = self._app.settings
        pad = {"padx": 12, "pady": 6}
        container = tk.Frame(self, padx=16, pady=14)
        container.pack(fill=tk.BOTH, expand=True)

        # ── Timeout portapapeles (FR-016, C-004) ──────────────────────────────
        tk.Label(
            container,
            text="Borrado de portapapeles (s):",
            anchor="w",
        ).grid(row=0, column=0, sticky="w", **pad)

        self._clip_var = tk.IntVar(value=s.clipboard_timeout_s)
        tk.Spinbox(
            container,
            from_=CLIPBOARD_TIMEOUT_MIN,
            to=CLIPBOARD_TIMEOUT_MAX,
            textvariable=self._clip_var,
            width=7,
        ).grid(row=0, column=1, sticky="w", **pad)

        tk.Label(
            container,
            text=f"({CLIPBOARD_TIMEOUT_MIN}–{CLIPBOARD_TIMEOUT_MAX} s)",
            fg="gray",
            font=("", 8),
            anchor="w",
        ).grid(row=0, column=2, sticky="w")

        # ── Timeout auto-bloqueo (FR-017) ─────────────────────────────────────
        tk.Label(
            container,
            text="Auto-bloqueo por inactividad (s):",
            anchor="w",
        ).grid(row=1, column=0, sticky="w", **pad)

        self._lock_var = tk.IntVar(value=s.auto_lock_timeout_s)
        tk.Spinbox(
            container,
            from_=AUTO_LOCK_TIMEOUT_MIN,
            to=AUTO_LOCK_TIMEOUT_MAX,
            textvariable=self._lock_var,
            width=7,
        ).grid(row=1, column=1, sticky="w", **pad)

        tk.Label(
            container,
            text=f"({AUTO_LOCK_TIMEOUT_MIN}–{AUTO_LOCK_TIMEOUT_MAX} s)",
            fg="gray",
            font=("", 8),
            anchor="w",
        ).grid(row=1, column=2, sticky="w")

        container.columnconfigure(0, weight=1)

        # ── Botones ───────────────────────────────────────────────────────────
        btn_frame = tk.Frame(container)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=(14, 0), sticky="e")

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

    def _on_save(self) -> None:
        """Valida, persiste y aplica la nueva configuración.

        Refs: T039 — «Guardar persiste AppSettings, actualiza VaultService».
        """
        try:
            clip = int(self._clip_var.get())
            lock = int(self._lock_var.get())
        except (ValueError, tk.TclError):
            messagebox.showerror(
                "Valor inválido",
                "Los valores deben ser números enteros.",
                parent=self,
            )
            return

        if not (CLIPBOARD_TIMEOUT_MIN <= clip <= CLIPBOARD_TIMEOUT_MAX):
            messagebox.showerror(
                "Valor fuera de rango",
                f"El timeout del portapapeles debe estar entre "
                f"{CLIPBOARD_TIMEOUT_MIN} y {CLIPBOARD_TIMEOUT_MAX} s.",
                parent=self,
            )
            return

        if not (AUTO_LOCK_TIMEOUT_MIN <= lock <= AUTO_LOCK_TIMEOUT_MAX):
            messagebox.showerror(
                "Valor fuera de rango",
                f"El timeout de auto-bloqueo debe estar entre "
                f"{AUTO_LOCK_TIMEOUT_MIN} y {AUTO_LOCK_TIMEOUT_MAX} s.",
                parent=self,
            )
            return

        # Persistir en disco
        new_settings = AppSettings(
            clipboard_timeout_s=clip,
            auto_lock_timeout_s=lock,
        )
        try:
            save_settings(APP_CONFIG_PATH, new_settings)
        except OSError as exc:
            messagebox.showerror(
                "Error al guardar",
                f"No se pudo guardar la configuración:\n{exc}",
                parent=self,
            )
            return

        # Actualizar App y VaultService en caliente
        self._app.settings = new_settings
        self._app.service.set_auto_lock_timeout(lock)

        self.destroy()

