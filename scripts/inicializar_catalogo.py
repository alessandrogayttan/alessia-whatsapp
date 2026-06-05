"""
Crea la hoja 'Catalogo' en tu Google Sheet (Drive) con encabezados y catálogo
alineado con inpulso43.com.
Ejecutar una vez: python scripts/inicializar_catalogo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from catalogo import CATALOGO_TAB, HEADERS
from catalogo_web import filas_catalogo_sheet
from google_client import get_sheets_service


def main():
    if not config.ID_HOJA_CALCULO:
        print("Configura ID_HOJA_CALCULO en .env")
        sys.exit(1)

    service = get_sheets_service()
    meta = service.spreadsheets().get(spreadsheetId=config.ID_HOJA_CALCULO).execute()
    tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]

    if CATALOGO_TAB not in tabs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=config.ID_HOJA_CALCULO,
            body={
                "requests": [
                    {"addSheet": {"properties": {"title": CATALOGO_TAB}}}
                ]
            },
        ).execute()
        print(f"Hoja '{CATALOGO_TAB}' creada.")

    filas = filas_catalogo_sheet()
    service.spreadsheets().values().update(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{CATALOGO_TAB}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [HEADERS] + filas},
    ).execute()

    print(f"Catálogo inicializado ({len(filas)} entradas) — alineado con {config.CLINICA_WEB_URL}")
    print(f"Abre tu Sheet en Drive:")
    print(f"https://docs.google.com/spreadsheets/d/{config.ID_HOJA_CALCULO}")
    print()
    print("Comparte el archivo con cada terapeuta (Editor) y con:")
    print("alessia-bot@agente-inpulso.iam.gserviceaccount.com (Editor)")


if __name__ == "__main__":
    main()
