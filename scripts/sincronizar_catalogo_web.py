"""
Actualiza modalidades y filas faltantes en la hoja Catalogo según inpulso43.com.
No borra entradas personalizadas de terapeutas; corrige modalidad y agrega lo que falte.

Ejecutar: python scripts/sincronizar_catalogo_web.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from catalogo import CATALOGO_TAB, _buscar_fila_catalogo, _filas_crudas_catalogo, invalidar_cache
from catalogo_web import MODALIDAD_PRESENCIAL_ONLINE, MODALIDAD_SOLO_ONLINE, filas_catalogo_sheet
from google_client import get_sheets_service


def _es_solo_online(terapeuta: str, nombre: str, modalidad: str) -> bool:
    texto = f"{terapeuta} {nombre} {modalidad}".lower()
    return "mentora" in texto


def main():
    if not config.ID_HOJA_CALCULO:
        print("Configura ID_HOJA_CALCULO en .env")
        sys.exit(1)

    service = get_sheets_service()
    existentes = _filas_crudas_catalogo()
    claves_existentes = set()
    actualizadas = 0

    for row in existentes:
        if len(row) < 3:
            continue
        terapeuta, nombre = row[0].strip(), row[2].strip()
        claves_existentes.add((terapeuta.lower(), nombre.lower()))
        modalidad_actual = row[5].strip() if len(row) > 5 else ""
        if _es_solo_online(terapeuta, nombre, modalidad_actual):
            nueva = MODALIDAD_SOLO_ONLINE
        else:
            nueva = MODALIDAD_PRESENCIAL_ONLINE
        if modalidad_actual.lower() != nueva.lower():
            fila_num = _buscar_fila_catalogo(terapeuta, nombre)
            if fila_num:
                service.spreadsheets().values().update(
                    spreadsheetId=config.ID_HOJA_CALCULO,
                    range=f"{CATALOGO_TAB}!F{fila_num}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[nueva]]},
                ).execute()
                actualizadas += 1
                print(f"  Modalidad → {nueva}: {terapeuta} / {nombre}")

    agregadas = 0
    for row in filas_catalogo_sheet():
        terapeuta, nombre = row[0], row[2]
        if (terapeuta.lower(), nombre.lower()) not in claves_existentes:
            service.spreadsheets().values().append(
                spreadsheetId=config.ID_HOJA_CALCULO,
                range=f"{CATALOGO_TAB}!A:J",
                valueInputOption="USER_ENTERED",
                body={"values": [row]},
            ).execute()
            agregadas += 1
            print(f"  + Agregado: {terapeuta} / {nombre}")

    invalidar_cache()
    print()
    print(f"Listo — {actualizadas} modalidades corregidas, {agregadas} filas nuevas.")
    print(f"Web: {config.CLINICA_WEB_URL}")


if __name__ == "__main__":
    main()
