"""Pestaña Analytics en Google Sheets: flujo de mensajes + heridas (con gráfico)."""
from __future__ import annotations

import logging
from datetime import datetime

import pytz

import config
import storage
from google_client import get_sheets_service

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)
TAB = "Analytics"
CHART_TITLE = "Mensajes y menciones de heridas (últimos 30 días)"


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
    """Línea: Fecha | Mensajes | Menciones heridas."""
    if num_filas_datos < 1:
        return
    end_row = 1 + num_filas_datos  # header + data (exclusive end in API is end index)
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
                                                "startRowIndex": 4,
                                                "endRowIndex": 4 + end_row,
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
                                                "startRowIndex": 4,
                                                "endRowIndex": 4 + end_row,
                                                "startColumnIndex": 1,
                                                "endColumnIndex": 2,
                                            }
                                        ]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS",
                            },
                            {
                                "series": {
                                    "sourceRange": {
                                        "sources": [
                                            {
                                                "sheetId": sheet_id,
                                                "startRowIndex": 4,
                                                "endRowIndex": 4 + end_row,
                                                "startColumnIndex": 2,
                                                "endColumnIndex": 3,
                                            }
                                        ]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS",
                            },
                        ],
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": sheet_id,
                            "rowIndex": 4,
                            "columnIndex": 5,
                        },
                        "widthPixels": 600,
                        "heightPixels": 360,
                    }
                },
            }
        }
    }
    service.spreadsheets().batchUpdate(
        spreadsheetId=config.ID_HOJA_CALCULO,
        body={"requests": [request]},
    ).execute()


def actualizar_analytics(*, dias: int = 30) -> str:
    """Escribe pestaña Analytics + gráfico en vivo (se refresca en cada sync)."""
    if not config.ID_HOJA_CALCULO:
        return "ID_HOJA_CALCULO no configurado"
    service = get_sheets_service()
    sheet_id = _asegurar_hoja(service)
    ahora = datetime.now(ZONA).strftime("%Y-%m-%d %H:%M")
    diarios = storage.metricas_mensajes_por_dia(dias)
    faq_heridas = storage.metricas_faq_heridas()
    interes = storage.metricas_interes_heridas()
    top = storage.top_preguntas_frecuentes(15)
    total_msgs = sum(int(d.get("mensajes") or 0) for d in diarios)
    total_heridas = sum(int(d.get("menciones_heridas") or 0) for d in diarios)

    resumen = [
        ["Analytics Alessia — Inpulso 43", "", "", ""],
        ["Actualizado", ahora, "", ""],
        [
            "Mensajes pacientes (periodo)",
            total_msgs,
            "Menciones heridas/historia",
            total_heridas,
        ],
        [
            "Interés talleres heridas (activo)",
            interes.get("interes_activo_relacionado", 0),
            "Interés heridas últimos 7 días",
            interes.get("interes_7d_heridas", 0),
        ],
        ["Fecha", "Mensajes", "Menciones heridas", ""],
    ]
    for d in diarios:
        resumen.append(
            [
                d.get("dia") or "",
                int(d.get("mensajes") or 0),
                int(d.get("menciones_heridas") or 0),
                "",
            ]
        )

    # Bloque FAQ heridas a la derecha del resumen (columna H)
    faq_block = [["Preguntas FAQ sobre heridas/historia", "Veces", "Última vez"]]
    for f in faq_heridas:
        faq_block.append(
            [f.get("pregunta") or "", int(f.get("veces") or 0), f.get("ultima_vez") or ""]
        )
    if len(faq_block) == 1:
        faq_block.append(["(aún no hay preguntas registradas)", 0, ""])

    top_block = [["Top preguntas generales", "Veces", "Última vez"]]
    for f in top:
        top_block.append(
            [f.get("pregunta") or "", int(f.get("veces") or 0), f.get("ultima_vez") or ""]
        )

    # Limpiar y escribir
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
    logger.info("Analytics actualizado (%s días, %s msgs)", dias, total_msgs)
    return url


def inicializar_analytics() -> str:
    return actualizar_analytics()
