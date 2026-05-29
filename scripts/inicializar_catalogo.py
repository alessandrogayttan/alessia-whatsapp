"""
Crea la hoja 'Catalogo' en tu Google Sheet (Drive) con encabezados y datos de ejemplo.
Ejecutar una vez: python scripts/inicializar_catalogo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from catalogo import CATALOGO_TAB, HEADERS
from google_client import get_sheets_service

EJEMPLOS = [
    [
        "Sara Rosales",
        "taller",
        "El cuerpo que aprendió a sobrevivir: la ansiedad después del control",
        "Lunes 1 y 8 de junio (2 sesiones)",
        "6:00 PM",
        "Presencial en Inpulso 43 y online",
        "Online $400 MXN / Presencial $500 MXN",
        "Cupo limitado",
        "Ansiedad: síntoma o problema; Origen profundo; Regulación emocional",
        "SI",
    ],
    ["Sara Rosales", "servicio", "Terapia individual", "", "", "Presencial", "$800", "", "", "SI"],
    ["Sara Rosales", "servicio", "Terapia de pareja", "", "", "Presencial", "$900", "", "", "SI"],
    ["Patricia", "servicio", "Terapia individual", "", "", "Presencial", "$800", "", "", "SI"],
    ["Iván", "servicio", "Terapia individual", "", "", "Presencial", "$800", "", "", "SI"],
    ["Juan", "servicio", "Terapia individual", "", "", "Presencial", "$1000", "", "", "SI"],
    ["Nutrición", "servicio", "Consulta nutricional", "", "", "Presencial", "$450", "", "", "SI"],
]


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

    service.spreadsheets().values().update(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{CATALOGO_TAB}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [HEADERS] + EJEMPLOS},
    ).execute()

    print("Catalogo inicializado con encabezados y ejemplos.")
    print(f"Abre tu Sheet en Drive y editalo:")
    print(f"https://docs.google.com/spreadsheets/d/{config.ID_HOJA_CALCULO}")
    print()
    print("Comparte el archivo con cada terapeuta (Editor) y con:")
    print("alessia-bot@agente-inpulso.iam.gserviceaccount.com (Editor)")


if __name__ == "__main__":
    main()
