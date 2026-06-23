"""Punto de entrada de la aplicación (T018).

Uso:
    python -m src.main
    # o desde la raíz del proyecto con PYTHONPATH=src:
    PYTHONPATH=src python src/main.py
"""
import sys
import tkinter as tk
from pathlib import Path

# Garantizar que src/ está en el path al ejecutar directamente
_SRC = Path(__file__).parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ui.app import App
from vault.service import VaultService


def main() -> None:
    root = tk.Tk()
    root.title("Gestor de Contraseñas")
    root.minsize(580, 420)
    root.resizable(True, True)

    service = VaultService()  # auto-bloqueo activado (300s por defecto)
    App(root, service)

    root.mainloop()


if __name__ == "__main__":
    main()
