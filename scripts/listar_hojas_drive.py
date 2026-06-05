"""Lista pestañas del Google Sheet de Inpulso."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from google_client import get_sheets_service

service = get_sheets_service()
meta = service.spreadsheets().get(spreadsheetId=config.ID_HOJA_CALCULO).execute()
for s in meta.get("sheets", []):
    p = s.get("properties", {})
    print(p.get("title"), "-", p.get("gridProperties", {}).get("rowCount"), "filas")
