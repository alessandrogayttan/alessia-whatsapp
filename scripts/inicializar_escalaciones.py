"""
Crea la hoja 'Escalaciones' en tu Google Sheet para HABLAR CON PERSONA.
Ejecutar una vez: python scripts/inicializar_escalaciones.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from google_client import get_sheets_service

HEADERS = ["Fecha", "Teléfono", "Nombre", "Motivo", "Estado", "Notas"]


def main():
    if not config.ID_HOJA_CALCULO:
        print("Configura ID_HOJA_CALCULO en .env")
        sys.exit(1)

    service = get_sheets_service()
    meta = service.spreadsheets().get(spreadsheetId=config.ID_HOJA_CALCULO).execute()
    tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]

    if "Escalaciones" not in tabs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=config.ID_HOJA_CALCULO,
            body={"requests": [{"addSheet": {"properties": {"title": "Escalaciones"}}}]},
        ).execute()
        print("Hoja 'Escalaciones' creada.")

    service.spreadsheets().values().update(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range="Escalaciones!A1:F1",
        valueInputOption="USER_ENTERED",
        body={"values": [HEADERS]},
    ).execute()

    print("Escalaciones listo. Recepción debe revisar esta hoja cuando un paciente escribe HABLAR CON PERSONA.")
    print(f"https://docs.google.com/spreadsheets/d/{config.ID_HOJA_CALCULO}")


if __name__ == "__main__":
    main()
