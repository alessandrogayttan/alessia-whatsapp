"""Crea/actualiza la pestaña Dashboard en Google Sheets."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import actualizar_dashboard

if __name__ == "__main__":
    actualizar_dashboard()
    print("Dashboard listo.")
