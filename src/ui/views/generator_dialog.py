"""Diálogo generador de contraseñas (T028).

Responsabilidades:
  - Spinbox para longitud (LENGTH_MIN–LENGTH_MAX).
  - Cuatro Checkbutton para conjuntos de caracteres (FR-014).
  - Botón "Generar" deshabilitado cuando ningún charset está activo.
  - Entry readonly que muestra la contraseña generada.
  - Botón "Regenerar" — produce un nuevo valor sin perder la configuración.
  - Botón "Usar esta contraseña" — entrega el valor al caller y cierra.

Refs: spec.md → US4 Acceptance Scenarios 1–4; FR-014.
      plan.md → src/ui/views/generator_dialog.py (Toplevel Tkinter).
      Constitución: Principio I — no expone datos sensibles fuera del flujo UI.
"""
import tkinter as tk
from tkinter import messagebox
from typing import Callable

from generator.password_generator import (
    LENGTH_MAX,
    LENGTH_MIN,
    generate_password,
)


class GeneratorDialog(tk.Toplevel):
    """Diálogo modal para generar contraseñas seguras configurables.

    Args:
        parent: Widget padre (normalmente EntryFormView).
        on_use: Callback invocado con la contraseña generada cuando el usuario
                pulsa "Usar esta contraseña". Recibe un único argumento str.

    Ejemplo::

        GeneratorDialog(self, on_use=self._password_var.set)
    """

    def __init__(self, parent: tk.Widget, on_use: Callable[[str], None]) -> None:
        super().__init__(parent)
        self.withdraw()          # ocultar hasta estar posicionada (Fix 1: sin parpadeo)
        self.title("Generador de contraseñas")
        self.resizable(False, False)

        self._on_use = on_use
        self._generated: str = ""

        self._build_ui()
        self._update_generate_btn()

        # Centrar sobre el padre y mostrar ya posicionado (Fix 1)
        self.update_idletasks()
        pw = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        ph = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{pw}+{ph}")
        self.deiconify()
        self.wait_visibility()
        self.grab_set()
        self.focus_set()

    # ── Construcción de la UI ─────────────────────────────────────────────────

    def _build_ui(self) -> None:
        container = tk.Frame(self, padx=16, pady=12)
        container.pack(fill=tk.BOTH, expand=True)

        # ── Longitud (FR-014: 8–128) ──────────────────────────────────────────
        length_row = tk.Frame(container)
        length_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(length_row, text="Longitud:", width=12, anchor="w").pack(side=tk.LEFT)
        self._length_var = tk.IntVar(value=16)
        tk.Spinbox(
            length_row,
            from_=LENGTH_MIN,
            to=LENGTH_MAX,
            textvariable=self._length_var,
            width=6,
        ).pack(side=tk.LEFT)

        # ── Conjuntos de caracteres (FR-014) ──────────────────────────────────
        charset_box = tk.LabelFrame(
            container, text="Conjuntos de caracteres", padx=8, pady=6
        )
        charset_box.pack(fill=tk.X, pady=(0, 10))

        self._use_upper = tk.BooleanVar(value=True)
        self._use_lower = tk.BooleanVar(value=True)
        self._use_digits = tk.BooleanVar(value=True)
        self._use_symbols = tk.BooleanVar(value=False)

        for text, var in (
            ("Mayúsculas  (A–Z)", self._use_upper),
            ("Minúsculas  (a–z)", self._use_lower),
            ("Dígitos  (0–9)", self._use_digits),
            ("Símbolos  (!@#…)", self._use_symbols),
        ):
            tk.Checkbutton(
                charset_box,
                text=text,
                variable=var,
                command=self._update_generate_btn,
                anchor="w",
            ).pack(fill=tk.X)

        # ── Botón Generar ─────────────────────────────────────────────────────
        self._generate_btn = tk.Button(
            container,
            text="Generar",
            command=self._generate,
            cursor="hand2",
            bg="#27ae60",
            fg="white",
            relief="flat",
            padx=12,
        )
        self._generate_btn.pack(pady=(0, 10))

        # ── Resultado (readonly) ──────────────────────────────────────────────
        result_box = tk.LabelFrame(container, text="Contraseña generada", padx=8, pady=6)
        result_box.pack(fill=tk.X, pady=(0, 10))
        self._result_var = tk.StringVar()
        self._result_entry = tk.Entry(
            result_box,
            textvariable=self._result_var,
            state="readonly",
            font=("Courier", 11),
            width=34,
        )
        self._result_entry.pack(fill=tk.X)

        # ── Barra de acciones ─────────────────────────────────────────────────
        btn_bar = tk.Frame(container)
        btn_bar.pack(fill=tk.X)

        tk.Button(
            btn_bar,
            text="Cancelar",
            command=self.destroy,
            cursor="hand2",
            width=10,
        ).pack(side=tk.RIGHT, padx=(4, 0))

        self._use_btn = tk.Button(
            btn_bar,
            text="Usar esta contraseña",
            command=self._use_password,
            cursor="hand2",
            bg="#2980b9",
            fg="white",
            relief="flat",
            state=tk.DISABLED,
            padx=8,
        )
        self._use_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self._regen_btn = tk.Button(
            btn_bar,
            text="Regenerar",
            command=self._generate,
            cursor="hand2",
            relief="flat",
            state=tk.DISABLED,
            padx=6,
        )
        self._regen_btn.pack(side=tk.RIGHT, padx=(4, 0))

    # ── Lógica ────────────────────────────────────────────────────────────────

    def _any_charset_active(self) -> bool:
        """True si al menos un conjunto de caracteres está habilitado."""
        return any([
            self._use_upper.get(),
            self._use_lower.get(),
            self._use_digits.get(),
            self._use_symbols.get(),
        ])

    def _update_generate_btn(self) -> None:
        """Habilita / deshabilita el botón Generar según los charsets activos.

        Ref: tasks.md → T028 — botón Generar deshabilitado si ningún charset activo.
        """
        state = tk.NORMAL if self._any_charset_active() else tk.DISABLED
        self._generate_btn.config(state=state)

    def _generate(self) -> None:
        """Genera una contraseña con la configuración actual y muestra el resultado.

        Refs: US4 Acceptance Scenario 2 (resultado cumple config),
              US4 Acceptance Scenario 4 (regenerar sin perder config).
        """
        try:
            length = int(self._length_var.get())
        except (ValueError, tk.TclError):
            messagebox.showerror(
                "Longitud inválida",
                f"Introduce un número entero entre {LENGTH_MIN} y {LENGTH_MAX}.",
                parent=self,
            )
            return

        try:
            password = generate_password(
                length=length,
                use_uppercase=self._use_upper.get(),
                use_lowercase=self._use_lower.get(),
                use_digits=self._use_digits.get(),
                use_symbols=self._use_symbols.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return

        self._generated = password
        self._result_var.set(password)
        # Habilitar acciones de uso y regeneración tras primera generación.
        self._use_btn.config(state=tk.NORMAL)
        self._regen_btn.config(state=tk.NORMAL)

    def _use_password(self) -> None:
        """Entrega la contraseña generada al campo del caller y cierra el diálogo.

        Ref: US4 Acceptance Scenario 3 — "Usar esta contraseña" rellena el campo.
        """
        if self._generated:
            self._on_use(self._generated)
        self.destroy()
