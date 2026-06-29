"""Diálogo modal para cambiar la contraseña maestra de la bóveda.

Responsabilidades (T019, T020, T021):
  - Tres campos Entry con show="*" y botón Mostrar/Ocultar por campo.
  - Indicador de fortaleza de la nueva contraseña (texto con color).
  - Pre-flight de validaciones en el hilo principal antes de lanzar el hilo de rotación.
  - Rotación no-bloqueante en hilo de fondo; resultado despachado con root.after().
  - suspend_auto_lock() antes de rotar; resume_auto_lock() siempre al terminar.
  - KeyRelease en los tres campos llama a record_activity() para reiniciar el timer.

Limitaciones conocidas de higiene de memoria — ver service.py:
  - Los objetos str en CPython son inmutables; las contraseñas no pueden zerorizarse.
    Se mitiga liberando referencias tan pronto como salen de scope y no almacenándolas
    en atributos de instancia más allá del tiempo de uso.
  - Los buffers internos de Argon2 (C) están fuera del control de Python.
  - El diálogo suspende el auto-bloqueo durante la operación activa. Si el usuario
    abandona el diálogo sin pulsar "Confirmar", el timer de inactividad corre con
    normalidad y teclear en los campos lo reinicia vía record_activity().

Refs: FR-001, FR-003, FR-015, FR-016, FR-018, FR-019, FR-020, FR-021,
      NFR-007, NFR-008, NFR-009.
Constitución: Principio I, V (auditabilidad), VII (UX consistente).
"""
import threading
import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING

from vault.exceptions import VaultLockedError, WrongPasswordError

if TYPE_CHECKING:
    from ui.app import App


# Umbrales para el indicador de fortaleza (FR-019, FR-020)
_STRENGTH_WEAK_MAX = 11   # < 12 → rojo
_STRENGTH_MEDIUM_MAX = 15  # 12–15 → ámbar
# ≥ 16 → verde


class ChangePasswordDialog(tk.Toplevel):
    """Ventana modal para rotar la contraseña maestra.

    Uso:
        dialog = ChangePasswordDialog(parent=root, app=app)
        dialog.grab_set()  # llamado externamente por MainView
    """

    def __init__(self, parent: tk.Widget, app: "App") -> None:
        super().__init__(parent)
        self._app = app
        self._rotation_in_progress = False

        self.title("Cambiar contraseña maestra")
        self.resizable(False, False)
        self.withdraw()  # ocultar hasta estar posicionada

        self._build_ui()
        self._center_over_parent(parent)
        self.deiconify()
        self.focus_force()

    # ── Construcción de UI (T019) ─────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = tk.Frame(self, padx=20, pady=16)
        outer.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            outer,
            text="Cambiar contraseña maestra",
            font=("", 12, "bold"),
        ).grid(row=0, column=0, columnspan=3, pady=(0, 12), sticky="w")

        # ── Campos de contraseña ──────────────────────────────────────────────
        labels = [
            "Contraseña actual:",
            "Nueva contraseña:",
            "Confirmar nueva contraseña:",
        ]
        self._entries: list[tk.Entry] = []
        self._show_vars: list[tk.BooleanVar] = []

        for row, label_text in enumerate(labels, start=1):
            tk.Label(outer, text=label_text, anchor="w").grid(
                row=row, column=0, sticky="w", pady=4
            )

            show_var = tk.BooleanVar(value=False)
            self._show_vars.append(show_var)

            entry = tk.Entry(outer, show="*", width=32)
            entry.grid(row=row, column=1, padx=(8, 4), pady=4)
            self._entries.append(entry)

            # T021: KeyRelease reinicia el timer de inactividad
            entry.bind("<KeyRelease>", self._on_key_release)

            # Botón Mostrar/Ocultar
            def _make_toggle(e=entry, v=show_var):
                def toggle():
                    v.set(not v.get())
                    e.config(show="" if v.get() else "*")
                return toggle

            tk.Button(
                outer,
                text="👁",
                command=_make_toggle(),
                relief="flat",
                cursor="hand2",
                padx=2,
            ).grid(row=row, column=2, padx=(0, 0))

        # ── Indicador de fortaleza (FR-020) ───────────────────────────────────
        self._strength_label = tk.Label(outer, text="", anchor="w")
        self._strength_label.grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(0, 4)
        )
        # Actualizar indicador cuando cambia el campo de nueva contraseña
        self._entries[1].bind("<KeyRelease>", self._on_new_password_key_release)

        # ── Label de estado / progreso ────────────────────────────────────────
        self._status_label = tk.Label(outer, text="", fg="gray", anchor="w")
        self._status_label.grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )

        # ── Botones Confirmar / Cancelar ──────────────────────────────────────
        btn_frame = tk.Frame(outer)
        btn_frame.grid(row=6, column=0, columnspan=3, pady=(4, 0))

        self._confirm_btn = tk.Button(
            btn_frame,
            text="Confirmar",
            command=self._on_confirm,
            bg="#27ae60",
            fg="white",
            relief="flat",
            padx=12,
            cursor="hand2",
        )
        self._confirm_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._cancel_btn = tk.Button(
            btn_frame,
            text="Cancelar",
            command=self._on_cancel,
            relief="flat",
            padx=12,
            cursor="hand2",
        )
        self._cancel_btn.pack(side=tk.LEFT)

    # ── Indicador de fortaleza (FR-020) ───────────────────────────────────────

    def _on_new_password_key_release(self, event: tk.Event) -> None:
        """Actualiza el indicador de fortaleza y llama a record_activity."""
        self._update_strength_indicator()
        self._app.service.record_activity()

    def _update_strength_indicator(self) -> None:
        pw = self._entries[1].get()
        length = len(pw)
        if not pw:
            self._strength_label.config(text="", fg="gray")
        elif length <= _STRENGTH_WEAK_MAX:
            self._strength_label.config(
                text=f"Fortaleza: Débil ({length} caracteres — mínimo 12)",
                fg="#e74c3c",
            )
        elif length <= _STRENGTH_MEDIUM_MAX:
            self._strength_label.config(
                text=f"Fortaleza: Media ({length} caracteres)",
                fg="#e67e22",
            )
        else:
            self._strength_label.config(
                text=f"Fortaleza: Fuerte ({length} caracteres)",
                fg="#27ae60",
            )

    # ── Actividad de usuario (T021) ───────────────────────────────────────────

    def _on_key_release(self, event: tk.Event) -> None:
        """KeyRelease en cualquier campo reinicia el timer de inactividad (FR-021).

        Nota: si el diálogo es abandonado sin pulsar "Confirmar", el timer de
        auto-bloqueo corre con normalidad y teclear aquí lo reinicia.
        """
        self._app.service.record_activity()

    # ── Lógica de rotación no-bloqueante (T020) ────────────────────────────────

    def _on_confirm(self) -> None:
        """Pre-flight en hilo principal, luego rotación en hilo de fondo."""
        if self._rotation_in_progress:
            return

        current_pw = self._entries[0].get()
        new_pw = self._entries[1].get()
        confirm_pw = self._entries[2].get()

        # (a) Pre-flight: validaciones baratas en hilo principal (FR-018, FR-019)
        if not new_pw:
            self._show_error("La nueva contraseña no puede estar vacía.")
            return
        if len(new_pw) < 12:
            self._show_error(
                f"La nueva contraseña debe tener al menos 12 caracteres (actual: {len(new_pw)})."
            )
            return
        if new_pw != confirm_pw:
            self._show_error("La nueva contraseña y su confirmación no coinciden.")
            return
        if new_pw == current_pw:
            self._show_error(
                "La nueva contraseña es idéntica a la actual. Elige una diferente."
            )
            return

        # (b) Suspender auto-bloqueo durante la rotación (FR-021)
        self._app.service.suspend_auto_lock()

        # (c) Deshabilitar botones y mostrar progreso
        self._rotation_in_progress = True
        self._confirm_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.DISABLED)
        self._status_label.config(text="Cambiando contraseña…", fg="gray")
        self.update_idletasks()

        # (d) Lanzar rotación en hilo de fondo (NFR-009 — sin bloqueo de UI)
        threading.Thread(
            target=self._run_rotation,
            args=(current_pw, new_pw),
            daemon=True,
        ).start()

    def _run_rotation(self, current_pw: str, new_pw: str) -> None:
        """Hilo de fondo: llama al servicio y despacha resultado al hilo principal.

        (e) Despachar resultado con root.after(0, callback) (Tkinter no es thread-safe).
        """
        try:
            self._app.service.change_master_password(current_pw, new_pw)
            self.after(0, self._on_success)
        except (WrongPasswordError, ValueError) as exc:
            self.after(0, self._on_error, str(exc))
        except Exception as exc:
            self.after(0, self._on_error, f"Error inesperado: {exc}")

    def _on_success(self) -> None:
        """(f) Éxito — ejecutado en hilo principal."""
        self._app.service.resume_auto_lock()
        messagebox.showinfo(
            "Contraseña cambiada",
            "La contraseña maestra ha sido cambiada con éxito.",
            parent=self,
        )
        self.destroy()

    def _on_error(self, message: str) -> None:
        """(f) Error — ejecutado en hilo principal."""
        self._app.service.resume_auto_lock()
        self._rotation_in_progress = False
        self._confirm_btn.config(state=tk.NORMAL)
        self._cancel_btn.config(state=tk.NORMAL)
        self._status_label.config(text="")
        self._show_error(message)

    def _on_cancel(self) -> None:
        """Cancela el diálogo si no hay rotación en progreso."""
        if not self._rotation_in_progress:
            self.destroy()

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _show_error(self, message: str) -> None:
        messagebox.showerror("Error", message, parent=self)

    def _center_over_parent(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w = self.winfo_reqwidth()
            h = self.winfo_reqheight()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
