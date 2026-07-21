#!/usr/bin/env python3
"""Genera EQUIPO_CLAVE_HASH para DigitalOcean / .env.

Uso:
  python scripts/hash_equipo_clave.py
  python scripts/hash_equipo_clave.py 'mi-contraseña'
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seguridad import hash_clave  # noqa: E402


def main() -> None:
    clave = sys.argv[1] if len(sys.argv) > 1 else getpass.getpass("Contraseña modo equipo: ")
    if not clave.strip():
        raise SystemExit("Contraseña vacía")
    print(hash_clave(clave.strip()))
    print("\nConfigura en el servidor:")
    print("  EQUIPO_CLAVE_HASH=<línea de arriba>")
    print("  EQUIPO_CLAVE_ACCESO=   (dejar vacío)")


if __name__ == "__main__":
    main()
