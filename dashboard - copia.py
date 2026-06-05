"""Actualiza pestaña Dashboard en Google Sheets."""
import datetime
import logging

import pytz

import config
import storage
from google_client import get_calendar_service, get_sheets_service

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)
TAB = "Dashboard"


def _asegurar_hoja_dashboard(service):
    meta = service.spreadsheets().get(spreadsheetId=config.ID_HOJA_CALCULO).execute()
    tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if TAB in tabs:
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=config.ID_HOJA_CALCULO,
        body={"requests": [{"addSheet": {"properties": {"title": TAB}}}]},
    ).execute()


def _contar_citas_semana() -> int:
    try:
        service = get_calendar_service()
        ahora = datetime.datetime.now(ZONA)
        fin = ahora + datetime.timedelta(days=7)
        total = 0
        for cal_id in config.DIRECTORIO_CALENDARIOS.values():
            events = service.events().list(
                calendarId=cal_id,
                timeMin=ahora.isoformat(),
                timeMax=fin.isoformat(),
                singleEvents=True,
            ).execute()
            total += len(events.get("items", []))
        return total
    except Exception as e:
        logger.warning("Error contando citas: %s", e)
        return 0


def _contar_inscripciones_mes() -> tuple[int, int]:
    if not config.ID_HOJA_CALCULO:
        return 0, 0
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Inscripciones!A:F"
        ).execute()
        rows = result.get("values", [])
        mes = datetime.datetime.now(ZONA).strftime("%Y-%m")
        pagados = pendientes = 0
        for row in rows[1:]:
            if row and row[0].startswith(mes):
                if len(row) > 5 and row[5] == "PAGADO":
                    pagados += 1
                elif len(row) > 5 and row[5] == "PENDIENTE":
                    pendientes += 1
        return pagados, pendientes
    except Exception as e:
        logger.warning("Error inscripciones dashboard: %s", e)
        return 0, 0


def _contar_escalaciones_pendientes() -> int:
    if not config.ID_HOJA_CALCULO:
        return 0
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Escalaciones!A:F"
        ).execute()
        rows = result.get("values", [])
        return sum(1 for r in rows[1:] if len(r) > 4 and r[4] == "PENDIENTE")
    except Exception:
        return 0


def actualizar_dashboard():
    if not config.ID_HOJA_CALCULO:
        return
    try:
        service = get_sheets_service()
        _asegurar_hoja_dashboard(service)
        ahora = datetime.datetime.now(ZONA).strftime("%Y-%m-%d %H:%M")
        citas_7d = _contar_citas_semana()
        pagados, pendientes = _contar_inscripciones_mes()
        escalaciones = _contar_escalaciones_pendientes()
        stats = storage.estadisticas_globales()
        valores = [
            ["Métrica", "Valor", "Actualizado"],
            ["Citas próximos 7 días", citas_7d, ahora],
            ["Talleres pagados (mes)", pagados, ahora],
            ["Talleres pendientes pago (mes)", pendientes, ahora],
            ["Escalaciones pendientes", escalaciones, ahora],
            ["Pacientes registrados", stats.get("pacientes", 0), ahora],
            ["Referidos activados", stats.get("referidos", 0), ahora],
            ["Check-ins emocionales (mes)", stats.get("checkins_mes", 0), ahora],
        ]
        service.spreadsheets().values().update(
            spreadsheetId=config.ID_HOJA_CALCULO,
            range=f"{TAB}!A1:C8",
            valueInputOption="USER_ENTERED",
            body={"values": valores},
        ).execute()
        logger.info("Dashboard actualizado")
    except Exception as e:
        logger.error("Error dashboard: %s", e)
