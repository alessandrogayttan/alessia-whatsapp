"""
Desactiva filas duplicadas/antiguas en la hoja Catalogo (columna Activo = NO).
Mantiene las entradas alineadas con inpulso43.com (nombres completos).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from catalogo import CATALOGO_TAB, _buscar_fila_catalogo, _filas_crudas_catalogo, invalidar_cache
from google_client import get_sheets_service

# Terapeuta antiguo -> nombre canónico en catálogo nuevo
REEMPLAZOS = {
    "patricia": "Patricia Velázquez",
    "iván": "Ivan Narro",
    "ivan": "Ivan Narro",
    "juan": "Juan Rosales",
}

# Nombres cortos que ya no deben usarse si existe el canónico
LEGACY_TERAPEUTAS = {"patricia", "iván", "ivan", "juan"}


def _activo(row: list) -> bool:
    raw = (row[9] if len(row) > 9 else "SI").strip().upper()
    return raw in ("SI", "SÍ", "S", "YES", "1", "TRUE")


def _clave(row: list) -> tuple[str, str, str]:
    terapeuta = row[0].strip() if len(row) > 0 else ""
    tipo = (row[1].strip().lower() if len(row) > 1 else "")
    nombre = row[2].strip() if len(row) > 2 else ""
    return terapeuta.lower(), tipo, nombre.lower()


def main():
    if not config.ID_HOJA_CALCULO:
        print("Configura ID_HOJA_CALCULO en .env")
        sys.exit(1)

    rows = _filas_crudas_catalogo()
    if not rows:
        print("Hoja Catalogo vacia.")
        return

    # Conjunto de claves canónicas presentes
    canonicas = set()
    for row in rows:
        if len(row) < 3 or not _activo(row):
            continue
        t = row[0].strip().lower()
        canonicas.add(_clave(row))

    service = get_sheets_service()
    desactivadas = 0

    for row in rows:
        if len(row) < 3 or not _activo(row):
            continue
        terapeuta = row[0].strip()
        t_lower = terapeuta.lower()
        nombre = row[2].strip() if len(row) > 2 else ""
        tipo = row[1].strip() if len(row) > 1 else ""

        motivo = None
        if t_lower in LEGACY_TERAPEUTAS:
            canon = REEMPLAZOS.get(t_lower, "")
            if canon:
                canon_row = None
                for r in rows:
                    if len(r) < 3:
                        continue
                    if (
                        r[0].strip() == canon
                        and (r[1].strip().lower() if len(r) > 1 else "") == tipo.lower()
                        and (r[2].strip() if len(r) > 2 else "") == nombre
                        and _activo(r)
                    ):
                        canon_row = r
                        break
                if canon_row:
                    motivo = f"duplicado de {canon}"

        # Sara: si falta terapia familiar antigua pero hay fila nueva, ok
        # Desactivar filas sin tipo o sin nombre
        if not nombre or not tipo:
            motivo = motivo or "fila incompleta"

        if not motivo:
            continue

        fila_num = _buscar_fila_catalogo(terapeuta, nombre)
        if not fila_num:
            continue

        service.spreadsheets().values().update(
            spreadsheetId=config.ID_HOJA_CALCULO,
            range=f"{CATALOGO_TAB}!J{fila_num}",
            valueInputOption="USER_ENTERED",
            body={"values": [["NO"]]},
        ).execute()
        desactivadas += 1
        print(f"  Desactivada ({motivo}): {terapeuta} / {tipo} / {nombre}")

    invalidar_cache()
    print()
    print(f"Listo: {desactivadas} fila(s) desactivadas en Catalogo.")
    print(f"Sheet: https://docs.google.com/spreadsheets/d/{config.ID_HOJA_CALCULO}")


if __name__ == "__main__":
    main()
