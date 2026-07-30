"""Crea/actualiza pestañas del taller heridas en el Sheet principal de Alessia.

Uso:
  python scripts/crear_hoja_heridas.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import storage
    from heridas_sheet import actualizar_dashboard_heridas, url_hoja_heridas

    storage.init_db()
    url = actualizar_dashboard_heridas()
    print("OK — pestañas en el Sheet de Alessia:")
    print("  Heridas_Cupo  (barra 0–100 + gráficas)")
    print("  Heridas_Inscritos")
    print("  Heridas_Interesados")
    print("URL:", url or url_hoja_heridas())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
