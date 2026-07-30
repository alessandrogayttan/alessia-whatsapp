"""Rellena pestañas del taller heridas + panel de cupo 0–100.

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
    from heridas_sheet import sincronizar_heridas_completo

    storage.init_db()
    out = sincronizar_heridas_completo()
    print("OK sync heridas:", out)
    print("Abre la pestaña Heridas_Cupo en el Sheet de Alessia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
