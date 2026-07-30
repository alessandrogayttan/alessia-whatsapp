"""Crea (o reutiliza) el Google Sheet exclusivo del taller de heridas.

Uso:
  python scripts/crear_hoja_heridas.py
  python scripts/crear_hoja_heridas.py --forzar
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Crea un archivo nuevo aunque ya exista un ID guardado",
    )
    args = parser.parse_args()

    import storage
    from heridas_sheet import asegurar_hoja_heridas, url_hoja_heridas

    storage.init_db()
    sid = asegurar_hoja_heridas(forzar_crear=args.forzar)
    url = url_hoja_heridas()
    print("OK spreadsheetId:", sid)
    print("URL:", url)
    print(
        "Revisa el correo de agenda.inpulso43@gmail.com (o HERIDAS_SHARE_EMAILS) "
        "y añade acceso directo a Mi unidad para tenerlo al inicio de Drive."
    )
    print("Opcional en DigitalOcean: ID_HOJA_HERIDAS=" + sid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
