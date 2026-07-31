"""Pestaña Analytics en Google Sheets: tablas compactas con color + gráfico."""
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
CHART_TITLE = "Actividad reciente — Alessia"

# Colores Inpulso (0–1 RGB para Sheets API)
AZUL = {"red": 0.18, "green": 0.31, "blue": 0.51}  # #2d4f82
ROJO = {"red": 0.78, "green": 0.29, "blue": 0.29}  # #C64A49
VERDE = {"red": 0.22, "green": 0.45, "blue": 0.38}
CREMA = {"red": 0.96, "green": 0.94, "blue": 0.90}
BLANCO = {"red": 1.0, "green": 1.0, "blue": 1.0}
GRIS = {"red": 0.45, "green": 0.45, "blue": 0.48}


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


def _paint(sheet_id: int, r0: int, r1: int, c0: int, c1: int, bg: dict, *, bold=False, white_text=False):
    fmt: dict = {"backgroundColor": bg}
    tf: dict = {}
    if bold:
        tf["bold"] = True
    if white_text:
        tf["foregroundColor"] = BLANCO
    if tf:
        fmt["textFormat"] = tf
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": r0,
                "endRowIndex": r1,
                "startColumnIndex": c0,
                "endColumnIndex": c1,
            },
            "cell": {"userEnteredFormat": fmt},
            "fields": "userEnteredFormat(backgroundColor,textFormat)",
        }
    }


def _col_widths(sheet_id: int) -> list[dict]:
    anchos = {0: 210, 1: 120, 2: 150, 3: 120, 4: 120, 6: 320, 7: 80, 8: 140}
    reqs = []
    for col, px in anchos.items():
        reqs.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": col,
                        "endIndex": col + 1,
                    },
                    "properties": {"pixelSize": px},
                    "fields": "pixelSize",
                }
            }
        )
    return reqs


def _quitar_charts(service, sheet_id: int) -> None:
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


def _crear_grafico(service, sheet_id: int, header_row: int, num_filas: int) -> None:
    """header_row = índice 0-based de la fila de encabezados de la tabla de actividad."""
    if num_filas < 1:
        return
    start = header_row
    end = header_row + 1 + num_filas
    _quitar_charts(service, sheet_id)
    request = {
        "addChart": {
            "chart": {
                "spec": {
                    "title": CHART_TITLE,
                    "basicChart": {
                        "chartType": "COLUMN",
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
                            "rowIndex": header_row,
                            "columnIndex": 6,
                        },
                        "widthPixels": 520,
                        "heightPixels": 300,
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
    """Solo citas de Alessia: eventos con 'Teléfono:' en la descripción."""
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
                    desc = event.get("description") or ""
                    if not re.search(r"Tel[eé]fono:\s*\+?[\d\s\-()]+", desc, re.I):
                        continue
                    start = event.get("start", {})
                    raw = start.get("dateTime") or start.get("date") or ""
                    dia = raw[:10]
                    if dia:
                        out[dia] += 1
                page_token = events.get("nextPageToken")
                if not page_token:
                    break
    except Exception as e:
        logger.warning("Analytics citas Alessia: %s", e)
    return dict(out)


def _inscripciones_por_dia() -> tuple[dict[str, int], int, int]:
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
        for row in result.get("values", [])[1:]:
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


def _tabla_actividad_compacta(
    diarios: list[dict],
    citas: dict[str, int],
    insc: dict[str, int],
    *,
    max_filas: int = 14,
) -> list[list]:
    """Solo días con movimiento; si no hay, últimos 7 días."""
    filas = []
    for d in diarios:
        dia = d.get("dia") or ""
        msgs = int(d.get("mensajes") or 0)
        her = int(d.get("menciones_heridas") or 0)
        cit = int(citas.get(dia, 0))
        ins = int(insc.get(dia, 0))
        if msgs or her or cit or ins:
            filas.append([dia, msgs, her, cit, ins])
    if not filas:
        for d in diarios[-7:]:
            dia = d.get("dia") or ""
            filas.append(
                [
                    dia,
                    int(d.get("mensajes") or 0),
                    int(d.get("menciones_heridas") or 0),
                    int(citas.get(dia, 0)),
                    int(insc.get(dia, 0)),
                ]
            )
    return filas[-max_filas:]


def actualizar_analytics(*, dias: int = 90, con_grafico: bool = True) -> str:
    if not config.ID_HOJA_CALCULO:
        return "ID_HOJA_CALCULO no configurado"

    service = get_sheets_service()
    sheet_id = _asegurar_hoja(service)
    ahora = datetime.now(ZONA).strftime("%Y-%m-%d %H:%M")

    diarios = storage.metricas_mensajes_por_dia(dias)
    hist = storage.metricas_resumen_historico()
    faq_heridas = storage.metricas_faq_heridas()
    faq_todas = storage.top_preguntas_frecuentes(100)
    recientes = storage.mensajes_recientes_pacientes(60)
    interes = storage.metricas_interes_heridas()
    citas = _citas_por_dia(dias)
    insc_dia, insc_pag, insc_pend = _inscripciones_por_dia()
    actividad = _tabla_actividad_compacta(diarios, citas, insc_dia)

    total_citas = sum(citas.values())
    nota = "Solo Alessia · incluye FAQ con WhatsApp y últimos mensajes"
    if hist.get("mensajes_totales", 0) == 0 and total_citas > 0:
        nota = "Hay citas Alessia; chats/FAQ se irán llenando con el uso"
    elif hist.get("mensajes_totales", 0) == 0 and total_citas == 0:
        nota = "Sin actividad Alessia todavía — se llenará con el uso"

    # Filas estimadas: título + resumen + actividad + FAQ + recientes
    filas_est = (
        20
        + len(actividad)
        + 3
        + max(len(faq_todas), 1)
        + 3
        + max(len(recientes), 1)
        + 5
    )
    grid: list[list] = [[""] * 10 for _ in range(max(filas_est, 50))]

    def put(r: int, c: int, val):
        while len(grid) <= r:
            grid.append([""] * 10)
        row = grid[r]
        while len(row) <= c:
            row.append("")
        row[c] = val

    put(0, 0, "Analytics Alessia · Inpulso 43")
    put(1, 0, f"Actualizado: {ahora}")
    put(1, 2, nota)

    put(3, 0, "1. RESUMEN (solo Alessia)")
    put(4, 0, "Métrica")
    put(4, 1, "Valor")
    kpis = [
        ("Mensajes guardados (historial Alessia)", hist.get("mensajes_totales", 0)),
        ("Mensajes de pacientes", hist.get("mensajes_pacientes", 0)),
        ("Menciones heridas / historia", hist.get("menciones_heridas_totales", 0)),
        ("Preguntas FAQ distintas", hist.get("faq_preguntas_distintas", 0)),
        ("Preguntas FAQ (veces totales)", hist.get("faq_veces_totales", 0)),
        ("Pacientes registrados por Alessia", hist.get("pacientes", 0)),
        ("Interés talleres (lista Alessia)", hist.get("interes_talleres_activo", 0)),
        ("Citas agendadas por Alessia (90 d)", total_citas),
        ("Inscripciones registradas", insc_pag),
        ("Inscripciones pendientes de pago", insc_pend),
        ("Interés heridas (últimos 7 d)", interes.get("interes_7d_heridas", 0)),
    ]
    for i, (label, val) in enumerate(kpis):
        put(5 + i, 0, label)
        put(5 + i, 1, val)

    act_title_row = 17
    act_header_row = 18
    put(act_title_row, 0, "2. ACTIVIDAD ALESSIA (máx. 14 días con movimiento)")
    put(act_header_row, 0, "Fecha")
    put(act_header_row, 1, "Mensajes")
    put(act_header_row, 2, "Heridas")
    put(act_header_row, 3, "Citas Alessia")
    put(act_header_row, 4, "Inscripciones")
    for i, fila in enumerate(actividad):
        for j, val in enumerate(fila):
            put(act_header_row + 1 + i, j, val)
    if not actividad:
        put(act_header_row + 1, 0, "(sin datos aún)")

    # 3. FAQ completa con WhatsApp (debajo de actividad)
    faq_title = act_header_row + 1 + max(len(actividad), 1) + 2
    faq_header = faq_title + 1
    put(faq_title, 0, "3. TODAS LAS PREGUNTAS FAQ (con WhatsApp del último que preguntó)")
    put(faq_header, 0, "Pregunta")
    put(faq_header, 1, "Veces")
    put(faq_header, 2, "Última vez")
    put(faq_header, 3, "WhatsApp")
    put(faq_header, 4, "¿Heridas?")
    if faq_todas:
        heridas_set = {f.get("pregunta") for f in faq_heridas}
        for i, f in enumerate(faq_todas):
            preg = f.get("pregunta") or ""
            put(faq_header + 1 + i, 0, preg[:120])
            put(faq_header + 1 + i, 1, int(f.get("veces") or 0))
            put(faq_header + 1 + i, 2, (f.get("ultima_vez") or "")[:19])
            put(faq_header + 1 + i, 3, f.get("ejemplo_telefono") or "")
            put(faq_header + 1 + i, 4, "Sí" if preg in heridas_set else "")
    else:
        put(faq_header + 1, 0, "(aún sin FAQ — se llenan al preguntar a Alessia)")

    # 4. Últimos mensajes crudos
    msg_title = faq_header + 1 + max(len(faq_todas), 1) + 2
    msg_header = msg_title + 1
    put(msg_title, 0, "4. ÚLTIMOS MENSAJES A ALESSIA (historial reciente)")
    put(msg_header, 0, "Fecha")
    put(msg_header, 1, "WhatsApp / sesión")
    put(msg_header, 2, "Canal")
    put(msg_header, 3, "Mensaje")
    if recientes:
        for i, m in enumerate(recientes):
            put(msg_header + 1 + i, 0, (m.get("creado_at") or "")[:19])
            put(msg_header + 1 + i, 1, m.get("telefono") or "")
            put(msg_header + 1 + i, 2, m.get("canal") or "")
            put(msg_header + 1 + i, 3, (m.get("contenido") or "")[:200])
    else:
        put(msg_header + 1, 0, "(sin mensajes guardados aún en el historial)")

    # Panel derecho breve: solo heridas destacadas
    put(3, 6, "HERIDAS — ver pestaña Heridas_Cupo")
    put(4, 6, "Pregunta")
    put(4, 7, "Veces")
    put(4, 8, "WhatsApp")
    if faq_heridas:
        for i, f in enumerate(faq_heridas[:15]):
            put(5 + i, 6, (f.get("pregunta") or "")[:70])
            put(5 + i, 7, int(f.get("veces") or 0))
            put(5 + i, 8, f.get("ejemplo_telefono") or "")
    else:
        put(5, 6, "(sin menciones aún)")

    service.spreadsheets().values().clear(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{TAB}!A:L",
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{TAB}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": grid},
    ).execute()

    n_act = max(len(actividad), 1)
    n_faq = max(len(faq_todas), 1)
    n_msg = max(len(recientes), 1)
    n_her = max(min(len(faq_heridas), 15), 1)
    fmt_reqs = _col_widths(sheet_id) + [
        _paint(sheet_id, 0, 1, 0, 5, AZUL, bold=True, white_text=True),
        _paint(sheet_id, 3, 4, 0, 2, AZUL, bold=True, white_text=True),
        _paint(sheet_id, 4, 5, 0, 2, CREMA, bold=True),
        _paint(sheet_id, 5, 5 + len(kpis), 0, 2, CREMA),
        _paint(sheet_id, act_title_row, act_title_row + 1, 0, 5, AZUL, bold=True, white_text=True),
        _paint(sheet_id, act_header_row, act_header_row + 1, 0, 5, CREMA, bold=True),
        _paint(sheet_id, act_header_row + 1, act_header_row + 1 + n_act, 0, 5, BLANCO),
        _paint(sheet_id, faq_title, faq_title + 1, 0, 5, VERDE, bold=True, white_text=True),
        _paint(sheet_id, faq_header, faq_header + 1, 0, 5, CREMA, bold=True),
        _paint(sheet_id, faq_header + 1, faq_header + 1 + n_faq, 0, 5, BLANCO),
        _paint(sheet_id, msg_title, msg_title + 1, 0, 4, AZUL, bold=True, white_text=True),
        _paint(sheet_id, msg_header, msg_header + 1, 0, 4, CREMA, bold=True),
        _paint(sheet_id, msg_header + 1, msg_header + 1 + n_msg, 0, 4, BLANCO),
        _paint(sheet_id, 3, 4, 6, 9, ROJO, bold=True, white_text=True),
        _paint(sheet_id, 4, 5, 6, 9, CREMA, bold=True),
        _paint(sheet_id, 5, 5 + n_her, 6, 9, BLANCO),
    ]
    try:
        service.spreadsheets().batchUpdate(
            spreadsheetId=config.ID_HOJA_CALCULO,
            body={"requests": fmt_reqs},
        ).execute()
    except Exception as e:
        logger.warning("Formato Analytics: %s", e)

    if con_grafico:
        try:
            _crear_grafico(service, sheet_id, act_header_row, len(actividad) or 1)
        except Exception as e:
            logger.warning("Gráfico Analytics: %s", e)

    url = (
        f"https://docs.google.com/spreadsheets/d/{config.ID_HOJA_CALCULO}/edit#gid={sheet_id}"
    )
    logger.info(
        "Analytics OK (faq=%s, msgs=%s, act=%s, grafico=%s)",
        len(faq_todas),
        len(recientes),
        len(actividad),
        con_grafico,
    )
    return url


def inicializar_analytics() -> str:
    return actualizar_analytics(dias=90)


def url_hoja_analytics() -> str:
    sid = (config.ID_HOJA_CALCULO or "").strip()
    if not sid:
        return ""
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit"


def sincronizar_panel_analytics() -> str:
    """Modo Pro / WhatsApp: datos Analytics sin recrear gráfico (más estable)."""
    try:
        url = actualizar_analytics(dias=90, con_grafico=False)
        storage.guardar_app_config("analytics_sync_ok", datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S"))
        storage.guardar_app_config("analytics_sync_error", "")
        storage.guardar_app_config("analytics_sync_detalle", str(url)[:500])
        return (
            "ÉXITO: Pestaña *Analytics* actualizada en Google Sheets.\n"
            f"• Link: {url or url_hoja_analytics()}\n"
            "Abre la pestaña *Analytics* (métricas, FAQ, actividad)."
        )
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        storage.guardar_app_config("analytics_sync_error", msg[:800])
        logger.exception("sincronizar_panel_analytics")
        return f"ERROR: No pude actualizar Analytics ({msg})."


def es_pedido_sync_panel_analytics(texto: str) -> bool:
    if not texto:
        return False
    n = texto.lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        n = n.replace(a, b)
    n = re.sub(r"\s+", " ", n).strip()
    if "analytic" not in n and "analitica" not in n and "analiticas" not in n:
        return False
    if re.search(
        r"(sincroniz\w*|actualiz\w*|llen\w*|refresc\w*|sync)\w*.{0,40}"
        r"(hoja|sheet|panel|pestana|tab|analytic)",
        n,
    ):
        return True
    if re.search(r"(hoja|panel|sheet).{0,30}analytic", n) and re.search(
        r"(sincroniz|actualiz|llen|refresc|sync)", n
    ):
        return True
    if re.search(r"\b(sync|sincroniza|sincronizar|actualiza|actualizar)\s+analytics?\b", n):
        return True
    return False


def intentar_comando_sync_analytics(
    telefono: str,
    texto: str,
    *,
    requerir_modo_pro: bool = True,
) -> str | None:
    if not es_pedido_sync_panel_analytics(texto):
        return None
    if requerir_modo_pro and not storage.sesion_equipo_activa(telefono):
        return None
    quien = (
        config.identificar_personal_inpulso(telefono)
        or storage.obtener_nombre_equipo_sesion(telefono)
        or "Equipo"
    )
    logger.info("Sync analytics por Modo Pro de %s (%s)", quien, telefono[-4:])
    resultado = sincronizar_panel_analytics()
    return f"Listo, *{quien}* ✨\n\n{resultado}"
