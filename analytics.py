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
VERDE = {"red": 0.22, "green": 0.55, "blue": 0.38}
NARANJA = {"red": 0.95, "green": 0.60, "blue": 0.20}
CREMA = {"red": 0.96, "green": 0.94, "blue": 0.90}
BLANCO = {"red": 1.0, "green": 1.0, "blue": 1.0}
GRIS = {"red": 0.88, "green": 0.88, "blue": 0.90}
BARRA_CELDAS = 20  # 5% cada celda


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


def _color_barra(pct: float, i: int, llenas: int) -> dict:
    if i >= llenas:
        return GRIS
    if pct >= 90:
        return ROJO
    if pct >= 70:
        return NARANJA
    return VERDE


def _crear_graficos_heridas(service, sheet_id: int) -> None:
    """Pie cupo + columnas pagos en Analytics."""
    _quitar_charts(service, sheet_id)
    charts = [
        {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Cupo presencial heridas (ocupados vs libres)",
                        "pieChart": {
                            "legendPosition": "RIGHT_LEGEND",
                            "domain": {
                                "sourceRange": {
                                    "sources": [
                                        {
                                            "sheetId": sheet_id,
                                            "startRowIndex": 14,
                                            "endRowIndex": 17,
                                            "startColumnIndex": 3,
                                            "endColumnIndex": 4,
                                        }
                                    ]
                                }
                            },
                            "series": {
                                "sourceRange": {
                                    "sources": [
                                        {
                                            "sheetId": sheet_id,
                                            "startRowIndex": 14,
                                            "endRowIndex": 17,
                                            "startColumnIndex": 4,
                                            "endColumnIndex": 5,
                                        }
                                    ]
                                }
                            },
                        },
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": sheet_id,
                                "rowIndex": 3,
                                "columnIndex": 7,
                            },
                            "widthPixels": 360,
                            "heightPixels": 240,
                        }
                    },
                }
            }
        },
        {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Pagos inscritos heridas",
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
                                                    "startRowIndex": 14,
                                                    "endRowIndex": 18,
                                                    "startColumnIndex": 6,
                                                    "endColumnIndex": 7,
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
                                                    "startRowIndex": 14,
                                                    "endRowIndex": 18,
                                                    "startColumnIndex": 7,
                                                    "endColumnIndex": 8,
                                                }
                                            ]
                                        }
                                    },
                                    "targetAxis": "LEFT_AXIS",
                                }
                            ],
                        },
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": sheet_id,
                                "rowIndex": 16,
                                "columnIndex": 7,
                            },
                            "widthPixels": 360,
                            "heightPixels": 220,
                        }
                    },
                }
            }
        },
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=config.ID_HOJA_CALCULO,
        body={"requests": charts},
    ).execute()


def actualizar_analytics(
    *,
    dias: int = 90,
    con_grafico: bool = True,
    con_formato: bool = True,
    con_calendario: bool = True,
) -> str:
    """Pestaña Analytics centrada en taller heridas + actividad Alessia."""
    if not config.ID_HOJA_CALCULO:
        return "ID_HOJA_CALCULO no configurado"

    from heridas_sheet import obtener_resumen_taller_heridas

    service = get_sheets_service()
    sheet_id = _asegurar_hoja(service)
    ahora = datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")

    cupo = obtener_resumen_taller_heridas()
    diarios = storage.metricas_mensajes_por_dia(dias)
    hist = storage.metricas_resumen_historico()
    faq_heridas = storage.metricas_faq_heridas()
    faq_todas = storage.top_preguntas_frecuentes(40)
    recientes = storage.mensajes_recientes_pacientes(40)
    interes = storage.metricas_interes_heridas()
    citas = _citas_por_dia(dias) if con_calendario else {}
    insc_dia, insc_pag, insc_pend = _inscripciones_por_dia()
    actividad = _tabla_actividad_compacta(diarios, citas, insc_dia)

    n_pres = int(cupo.get("presencial") or 0)
    meta = int(cupo.get("meta") or 100)
    pct = float(cupo.get("pct") or 0)
    libres = int(cupo.get("libres") or max(0, meta - n_pres))
    llenas = int(round(pct / (100 / BARRA_CELDAS))) if meta else 0
    llenas = max(0, min(BARRA_CELDAS, llenas))

    filas_est = 55 + len(actividad) + len(faq_todas) + len(recientes)
    grid: list[list] = [[""] * 12 for _ in range(max(filas_est, 70))]

    def put(r: int, c: int, val):
        while len(grid) <= r:
            grid.append([""] * 12)
        row = grid[r]
        while len(row) <= c:
            row.append("")
        row[c] = val

    put(0, 0, "ANALYTICS · Taller Sanando tus heridas del pasado + Alessia")
    put(1, 0, f"Actualizado: {ahora} (hora México) — sync automático")
    put(1, 4, "Meta presencial")
    put(1, 5, meta)

    put(3, 0, "1. CUPO PRESENCIAL HERIDAS (barra 0 a 100)")
    put(4, 0, "Inscritos presencial")
    put(4, 1, n_pres)
    put(5, 0, "Lugares libres")
    put(5, 1, libres)
    put(6, 0, "% llenado")
    put(6, 1, pct)
    put(6, 2, "%")
    put(7, 0, "Color: verde bajo 70% | naranja 70-89% | rojo 90%+")

    put(9, 0, "0%")
    put(9, BARRA_CELDAS - 1, "100%")
    for i in range(BARRA_CELDAS):
        put(10, i, "█" if i < llenas else "·")
    put(11, 0, f"{n_pres} / {meta} lugares presencial ocupados")

    put(13, 0, "RESUMEN TALLER HERIDAS")
    put(14, 0, "Métrica")
    put(14, 1, "Cantidad")
    resumen = [
        ("Inscritos totales", cupo.get("inscritos_total", 0)),
        ("Presencial (cupo)", n_pres),
        ("Online", cupo.get("online", 0)),
        ("Pagados", cupo.get("pagados", 0)),
        ("Pendientes de pago", cupo.get("pendientes", 0)),
        ("Interesados / preguntando", cupo.get("interesados", 0)),
        ("Interés heridas 7d (Alessia)", interes.get("interes_7d_heridas", 0)),
        ("Libres presencial", libres),
    ]
    for i, (k, v) in enumerate(resumen):
        put(15 + i, 0, k)
        put(15 + i, 1, v)

    put(14, 3, "Cupo presencial")
    put(14, 4, "Personas")
    put(15, 3, "Ocupados")
    put(15, 4, n_pres)
    put(16, 3, "Libres")
    put(16, 4, libres)

    put(14, 6, "Estatus pago")
    put(14, 7, "Cantidad")
    put(15, 6, "PAGADO")
    put(15, 7, cupo.get("pagados", 0))
    put(16, 6, "PENDIENTE")
    put(16, 7, cupo.get("pendientes", 0))
    put(17, 6, "Otros")
    put(
        17,
        7,
        max(
            0,
            int(cupo.get("inscritos_total") or 0)
            - int(cupo.get("pagados") or 0)
            - int(cupo.get("pendientes") or 0),
        ),
    )

    put(14, 9, "Embudo")
    put(14, 10, "Cantidad")
    put(15, 9, "Interesados")
    put(15, 10, cupo.get("interesados", 0))
    put(16, 9, "Inscritos")
    put(16, 10, cupo.get("inscritos_total", 0))

    act_title = 24
    act_header = 25
    put(act_title, 0, "2. ACTIVIDAD ALESSIA (días con movimiento)")
    put(act_header, 0, "Fecha")
    put(act_header, 1, "Mensajes")
    put(act_header, 2, "Heridas")
    put(act_header, 3, "Citas")
    put(act_header, 4, "Inscripciones")
    for i, fila in enumerate(actividad):
        for j, val in enumerate(fila):
            put(act_header + 1 + i, j, val)
    if not actividad:
        put(act_header + 1, 0, "(sin datos aún)")

    faq_title = act_header + 1 + max(len(actividad), 1) + 2
    faq_header = faq_title + 1
    put(faq_title, 0, "3. PREGUNTAS FAQ (prioridad heridas)")
    put(faq_header, 0, "Pregunta")
    put(faq_header, 1, "Veces")
    put(faq_header, 2, "Última vez")
    put(faq_header, 3, "WhatsApp")
    put(faq_header, 4, "¿Heridas?")
    heridas_set = {f.get("pregunta") for f in faq_heridas}
    ordenadas = sorted(
        faq_todas,
        key=lambda f: (0 if f.get("pregunta") in heridas_set else 1, -(f.get("veces") or 0)),
    )
    if ordenadas:
        for i, f in enumerate(ordenadas):
            preg = f.get("pregunta") or ""
            put(faq_header + 1 + i, 0, preg[:120])
            put(faq_header + 1 + i, 1, int(f.get("veces") or 0))
            put(faq_header + 1 + i, 2, (f.get("ultima_vez") or "")[:19])
            put(faq_header + 1 + i, 3, f.get("ejemplo_telefono") or "")
            put(faq_header + 1 + i, 4, "Sí" if preg in heridas_set else "")
    else:
        put(faq_header + 1, 0, "(aún sin FAQ)")

    msg_title = faq_header + 1 + max(len(ordenadas), 1) + 2
    msg_header = msg_title + 1
    put(msg_title, 0, "4. ÚLTIMOS MENSAJES A ALESSIA")
    put(msg_header, 0, "Fecha")
    put(msg_header, 1, "WhatsApp")
    put(msg_header, 2, "Canal")
    put(msg_header, 3, "Mensaje")
    if recientes:
        for i, m in enumerate(recientes):
            put(msg_header + 1 + i, 0, (m.get("creado_at") or "")[:19])
            put(msg_header + 1 + i, 1, m.get("telefono") or "")
            put(msg_header + 1 + i, 2, m.get("canal") or "")
            put(msg_header + 1 + i, 3, (m.get("contenido") or "")[:200])
    else:
        put(msg_header + 1, 0, "(sin mensajes)")

    put(3, 6, "KPIs ALESSIA")
    put(4, 6, "Mensajes totales")
    put(4, 7, hist.get("mensajes_totales", 0))
    put(5, 6, "Mensajes pacientes")
    put(5, 7, hist.get("mensajes_pacientes", 0))
    put(6, 6, "FAQ veces")
    put(6, 7, hist.get("faq_veces_totales", 0))
    put(7, 6, "Pacientes")
    put(7, 7, hist.get("pacientes", 0))
    put(8, 6, "Inscripciones Sheet")
    put(8, 7, insc_pag)

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

    if con_formato:
        fmt_reqs = _col_widths(sheet_id) + [
            _paint(sheet_id, 0, 1, 0, 8, AZUL, bold=True, white_text=True),
            _paint(sheet_id, 3, 4, 0, 6, ROJO, bold=True, white_text=True),
            _paint(sheet_id, 13, 14, 0, 2, VERDE, bold=True, white_text=True),
            _paint(sheet_id, 14, 15, 0, 2, CREMA, bold=True),
            _paint(sheet_id, 14, 15, 3, 5, CREMA, bold=True),
            _paint(sheet_id, 14, 15, 6, 8, CREMA, bold=True),
            _paint(sheet_id, 3, 4, 6, 8, AZUL, bold=True, white_text=True),
        ]
        for i in range(BARRA_CELDAS):
            bg = _color_barra(pct, i, llenas)
            fmt_reqs.append(
                _paint(sheet_id, 10, 11, i, i + 1, bg, bold=True, white_text=i < llenas)
            )
        try:
            service.spreadsheets().batchUpdate(
                spreadsheetId=config.ID_HOJA_CALCULO,
                body={"requests": fmt_reqs},
            ).execute()
        except Exception as e:
            logger.warning("Formato Analytics: %s", e)

    if con_grafico:
        try:
            _crear_graficos_heridas(service, sheet_id)
        except Exception as e:
            logger.warning("Gráficos heridas Analytics: %s", e)
        # Nota: _crear_grafico de actividad borra todos los charts; no lo llamamos aquí.

    url = (
        f"https://docs.google.com/spreadsheets/d/{config.ID_HOJA_CALCULO}/edit#gid={sheet_id}"
    )
    logger.info(
        "Analytics OK heridas pct=%s faq=%s grafico=%s",
        pct,
        len(ordenadas),
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
    """Actualiza Analytics con barra heridas 0-100, colores y gráficas."""
    try:
        url = actualizar_analytics(
            dias=60,
            con_grafico=True,
            con_formato=True,
            con_calendario=False,
        )
        storage.guardar_app_config(
            "analytics_sync_ok", datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")
        )
        storage.guardar_app_config("analytics_sync_error", "")
        storage.guardar_app_config("analytics_sync_detalle", str(url)[:500])
        return (
            "ÉXITO: Pestaña *Analytics* actualizada (cupo heridas + gráficas).\n"
            f"• Link: {url or url_hoja_analytics()}\n"
            "Abre la pestaña *Analytics*."
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
