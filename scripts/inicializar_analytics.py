"""Inicializa / refresca la pestaña Analytics en Google Sheets."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics import actualizar_analytics


if __name__ == "__main__":
    url = actualizar_analytics()
    print(url)
    print(
        "Abre esa URL: verás mensajes/día, menciones de heridas y el gráfico en vivo "
        "(se actualiza solo cada hora en producción)."
    )
