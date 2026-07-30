"""Pestaña Analytics en Google Sheets: flujo histórico + heridas (con gráfico)."""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta

import pytz

import config
import storage
from google_client import get_calendar_service, get_sheets_service

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)
TAB = "Analytics"
CHART_TITLE = "Actividad Alessia (mensajes, heridas y citas)"


def _sheet_id(service, titulo: str) -> int | None:
    meta = service.spreadsheets().get(spreadsheetId=config.ID_HOJA_CALCULO).execute()
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == titulo:
            return props.get("sheetId")
    return None


def _asegurar_hoja(service) -> int:
    sid = _sheet_id(service, TAB)
    if sid is not None:
        return sid
    res = (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=config.ID_HOJA_CALCULO,
            body={"requests": [{"addSheet": {"properties": {"title": TAB}}}]},
        )
        .execute()
    )
    return res["replies"][0]["addSheet"]["properties"]["sheetId"]


def _quitar_charts_analytics(service, sheet_id: int) -> None:
    meta = service.spreadsheets().get(
        spreadsheetId=config.ID_HOJA_CALCULO,
        fields="sheets(properties,charts)",
    ).execute()
    requests = []
    for s in meta.get("sheets", []):
        if s.get("properties", {}).get("sheetId") != sheet_id:
            continue
        for chart in s.get("charts", []) or []:
            cid = chart.get("chartId")
            if cid is not None:
                requests.append({"deleteEmbeddedObject": {"objectId": cid}})
    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=config.ID_HOJA_CALCULO,
            body={"requests": requests},
        ).execute()


def _crear_grafico(service, sheet_id: int, num_filas_datos: int) -> None:
    if num_filas_datos < 1:
        return
    # Header en fila índice 8 (tras resumen ampliado)
    start = 8
    end = start + 1 + num_filas_datos
    _quitar_charts_analytics(service, sheet_id)
    request = {
        "addChart": {
            "chart": {
                "spec": {
                    "title": CHART_TITLE,
                    "basicChart": {
                        "chartType": "LINE",
                        "legendPosition": "BOTTOM_LEGEND",
                        "headerCount": 1,
                        "domains": [
                            {
                                "domain": {
                                    "sourceRange": {
                                        "sources": [
                                            {
                                                "sheetId": sheet_id,
                                                "startRowIndex": start,
                                                "endRowIndex": end,
                                                "startColumnIndex": 0,
                                                "endColumnIndex": 1,
                                            }
                                        ]
                                    }
                                }
                            }
                        ],
                        "series": [
                            {
                                "series": {
                                    "sourceRange": {
                                        "sources": [
                                            {
                                                "sheetId": sheet_id,
                                                "startRowIndex": start,
                                                "endRowIndex": end,
                                                "startColumnIndex": col,
                                                "endColumnIndex": col + 1,
                                            }
                                        ]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS",
                            }
                            for col in (1, 2, 3)
                        ],
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": sheet_id,
                            "rowIndex": start,
                            "columnIndex": 6,
                        },
                        "widthPixels": 680,
                        "heightPixels": 380,
                    }
                },
            }
        }
    }
    service.spreadsheets().batchUpdate(
        spreadsheetId=config.ID_HOJA_CALCULO,
        body={"requests": [request]},
    ).execute()


def _citas_por_dia(dias: int = 90) -> dict[str, int]:
    """Cuenta eventos en calendarios de terapeutas (proxy de actividad histórica)."""
    out: dict[str, int] = defaultdict(int)
    try:
        service = get_calendar_service()
        ahora = datetime.now(ZONA)
        inicio = ahora - timedelta(days=dias)
        for cal_id in config.DIRECTORIO_CALENDARIOS.values():
            page_token = None
            while True:
                events = (
                    service.events()
                    .list(
                        calendarId=cal_id,
                        timeMin=inicio.isoformat(),
                        timeMax=(ahora + timedelta(days=1)).isoformat(),
                        singleEvents=True,
                        orderBy="startTime",
                        pageToken=page_token,
                        maxResults=2500,
                    )
                    .execute()
                )
                for event in events.get("items", []):
                    start = event.get("start", {})
                    raw = start.get("dateTime") or start.get("date") or ""
                    dia = raw[:10]
                    if dia:
                        out[dia] += 1
                page_token = events.get("nextPageToken")
                if not page_token:
                    break
    except Exception as e:
        logger.warning("Analytics citas Calendar: %s", e)
    return dict(out)


def _inscripciones_por_dia() -> tuple[dict[str, int], int, int]:
    """Lee pestaña Inscripciones del Sheet si existe."""
    por_dia: dict[str, int] = defaultdict(int)
    pagados = pendientes = 0
    if not config.ID_HOJA_CALCULO:
        return {}, 0, 0
    try:
        service = get_sheets_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=config.ID_HOJA_CALCULO, range="Inscripciones!A:F")
            .execute()
        )
        rows = result.get("values", [])
        for row in rows[1:]:
            if not row:
                continue
            m = re.match(r"(\d{4}-\d{2}-\d{2})", str(row[0]))
            if m:
                por_dia[m.group(1)] += 1
            estado = row[5].upper() if len(row) > 5 else ""
            if estado == "PAGADO":
                pagados += 1
            elif estado == "PENDIENTE":
                pendientes += 1
    except Exception as e:
        logger.warning("Analytics Inscripciones: %s", e)
    return dict(por_dia), pagados, pendientes


def actualizar_analytics(*, dias: int = 90) -> str:
    """Escribe Analytics con historial de BD + citas Calendar + Inscripciones."""
    if not config.ID_HOJA_CALCULO:
        return "ID_HOJA_CALCULO no configurado"
    service = get_sheets_service()
    sheet_id = _asegurar_hoja(service)
    ahora = datetime.now(ZONA).strftime("%Y-%m-%d %H:%M")
    diarios = storage.metricas_mensajes_por_dia(dias)
    hist = storage.metricas_resumen_historico()
    faq_heridas = storage.metricas_faq_heridas()
    interes = storage.metricas_interes_heridas()
    top = storage.top_preguntas_frecuentes(25)
    citas = _citas_por_dia(dias)
    insc_dia, insc_pag, insc_pend = _inscripciones_por_dia()

    total_msgs = sum(int(d.get("mensajes") or 0) for d in diarios)
    total_heridas = sum(int(d.get("menciones_heridas") or 0) for d in diarios)
    total_citas = sum(citas.values())

    nota = ""
    if hist.get("mensajes_totales", 0) == 0 and total_citas == 0:
        nota = (
            "Aún no hay historial de chats en la BD del servidor. "
            "De ahora en adelante se irá llenando. Revisa también FAQ_Pacientes."
        )
    elif hist.get("mensajes_totales", 0) == 0 and total_citas > 0:
        nota = (
            "No hay chats guardados en BD (posible reinicio del disco), "
            "pero sí hay citas en Calendar / inscripciones en Sheets como histórico."
        )

    resumen = [
        ["Analytics Alessia — Inpulso 43 (histórico)", "", "", "", ""],
        ["Actualizado", ahora, "Periodo gráfico (días)", dias, ""],
        [
            "Mensajes en gráfico",
            total_msgs,
            "Menciones heridas (gráfico)",
            total_heridas,
            "",
        ],
        [
            "Mensajes TOTAL BD (desde inicio)",
            hist.get("mensajes_totales", 0),
            "Mensajes pacientes BD",
            hist.get("mensajes_pacientes", 0),
            "",
        ],
        [
            "Menciones heridas/historia (total BD)",
            hist.get("menciones_heridas_totales", 0),
            "FAQ veces totales",
            hist.get("faq_veces_totales", 0),
            "",
        ],
        [
            "Pacientes registrados",
            hist.get("pacientes", 0),
            "Interés talleres activo",
            hist.get("interes_talleres_activo", 0),
            "",
        ],
        [
            "Citas en calendarios (periodo)",
            total_citas,
            "Inscripciones pagadas / pendientes",
            f"{insc_pag} / {insc_pend}",
            "",
        ],
        [
            "Historial BD desde",
            hist.get("historial_desde") or "(sin chats)",
            "Hasta",
            hist.get("historial_hasta") or "(sin chats)",
            "",
        ],
        ["Nota", nota or "OK — datos combinados BD + Calendar + Sheets", "", "", ""],
        ["Fecha", "Mensajes chat", "Menciones heridas", "Citas Calendar", "Inscripciones"],
    ]

    for d in diarios:
        dia = d.get("dia") or ""
        resumen.append(
            [
                dia,
                int(d.get("mensajes") or 0),
                int(d.get("menciones_heridas") or 0),
                int(citas.get(dia, 0)),
                int(insc_dia.get(dia, 0)),
            ]
        )

    faq_block = [["Preguntas FAQ heridas/historia", "Veces", "Última vez"]]
    for f in faq_heridas:
        faq_block.append(
            [f.get("pregunta") or "", int(f.get("veces") or 0), f.get("ultima_vez") or ""]
        )
    if len(faq_block) == 1:
        faq_block.append(["(aún sin FAQ de heridas registradas)", 0, ""])

    top_block = [["Top preguntas generales (FAQ)", "Veces", "Última vez"]]
    for f in top:
        top_block.append(
            [f.get("pregunta") or "", int(f.get("veces") or 0), f.get("ultima_vez") or ""]
        )
    if len(top_block) == 1:
        top_block.append(["(aún sin FAQ)", 0, ""])

    service.spreadsheets().values().clear(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{TAB}!A:L",
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{TAB}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": resumen},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{TAB}!H1",
        valueInputOption="USER_ENTERED",
        body={"values": faq_block},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{TAB}!H{len(faq_block) + 3}",
        valueInputOption="USER_ENTERED",
        body={"values": top_block},
    ).execute()

    try:
        _crear_grafico(service, sheet_id, len(diarios))
    except Exception as e:
        logger.warning("No se pudo crear gráfico Analytics: %s", e)

    url = (
        f"https://docs.google.com/spreadsheets/d/{config.ID_HOJA_CALCULO}/edit#gid={sheet_id}"
    )
    logger.info(
        "Analytics actualizado (%sd, msgs=%s, citas=%s, hist=%s)",
        dias,
        total_msgs,
        total_citas,
        hist.get("mensajes_totales"),
    )
    return url


def inicializar_analytics() -> str:
    return actualizar_analytics(dias=90)
