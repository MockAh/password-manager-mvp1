"""Aplicación principal — contenedor de vistas y barra de herramientas (T017, T037).

Responsabilidades:
  - Gestionar la navegación entre vistas (show_view).
  - Mostrar barra de herramientas con botón de bloqueo cuando la bóveda esté abierta.
  - Recibir el callback de auto-bloqueo desde VaultService y volver a UnlockView.
  - Registrar toda actividad del usuario (tecla, clic, scroll) para reiniciar el
    temporizador de inactividad (record_activity) — T037, US7 Sc3.

Constitución: Principio VII — UX consistente; Principio VIII — rendimiento UI.
"""
import tkinter as tk
from typing import TYPE_CHECKING, Type

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
