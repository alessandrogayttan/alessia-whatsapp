"""Taller heridas: pestañas en el Sheet principal de Alessia (visible en Drive).

Usa ID_HOJA_CALCULO (el mismo archivo que ya tienen) para que siempre se vea.
Pestañas: Heridas_Cupo | Heridas_Inscritos | Heridas_Interesados
"""
from __future__ import annotations

import logging
import re
import threading
import unicodedata
from datetime import datetime, timedelta

import pytz

import config
import storage
from google_client import get_sheets_service

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)
# Si el sync no limpia el flag (deploy/hang), «ya quedó?» deja de decir «en proceso»
SYNC_PENDIENTE_MAX_MIN = 3

TAB_CUPO = "Heridas_Cupo"
TAB_INSCRITOS = "Heridas_Inscritos"
TAB_INTERESADOS = "Heridas_Interesados"

HEADERS_INSCRITOS = [
    "Fecha",
    "Nombre",
    "WhatsApp",
    "Correo",
    "Modalidad",
    "Estatus pago",
    "Monto",
    "Fuente",
    "Notas",
]
HEADERS_INTERESADOS = [
    "Fecha",
    "Nombre",
    "WhatsApp",
    "Consulta",
    "Fuente",
    "Estado",
    "Notas",
]

CUPO_PRESENCIAL = 100
BARRA_CELDAS = 20  # cada celda = 5%

AZUL = {"red": 0.18, "green": 0.31, "blue": 0.51}
ROJO = {"red": 0.78, "green": 0.29, "blue": 0.29}
VERDE = {"red": 0.22, "green": 0.55, "blue": 0.38}
CREMA = {"red": 0.96, "green": 0.94, "blue": 0.90}
BLANCO = {"red": 1.0, "green": 1.0, "blue": 1.0}
GRIS = {"red": 0.88, "green": 0.88, "blue": 0.90}
NARANJA = {"red": 0.95, "green": 0.60, "blue": 0.20}


def es_taller_heridas(nombre_taller: str) -> bool:
    n = (nombre_taller or "").lower()
    return any(
        x in n
        for x in (
            "heridas",
            "sanando",
            "taller del niño",
            "taller del nino",
            "niño interior",
            "nino interior",
        )
    )


def _ahora() -> str:
    return datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")


def _sid() -> str:
    return (config.ID_HOJA_CALCULO or "").strip()


def url_hoja_heridas() -> str:
    sid = _sid()
    if not sid:
        return ""
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit#gid=0"


def _sheet_ids(service) -> dict[str, int]:
    meta = service.spreadsheets().get(spreadsheetId=_sid()).execute()
    return {
        s["properties"]["title"]: s["properties"]["sheetId"]
        for s in meta.get("sheets", [])
    }


def _asegurar_tab(service, titulo: str, headers: list[str] | None = None) -> int:
    ids = _sheet_ids(service)
    if titulo not in ids:
        body = {"requests": [{"addSheet": {"properties": {"title": titulo}}}]}
        res = service.spreadsheets().batchUpdate(spreadsheetId=_sid(), body=body).execute()
        sid = res["replies"][0]["addSheet"]["properties"]["sheetId"]
    else:
        sid = ids[titulo]
    if headers:
        # Siempre asegura encabezados (tabs vacías quedaban en blanco)
        actual = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=_sid(), range=f"{titulo}!A1:I1")
            .execute()
            .get("values", [])
        )
        if not actual or not actual[0] or not str(actual[0][0]).strip():
            cols = chr(ord("A") + len(headers) - 1)
            service.spreadsheets().values().update(
                spreadsheetId=_sid(),
                range=f"{titulo}!A1:{cols}1",
                valueInputOption="USER_ENTERED",
                body={"values": [headers]},
            ).execute()
    return sid


def _escribir_tabla(service, tab: str, headers: list[str], filas: list[list]) -> None:
    """Escribe encabezados+filas. Nunca deja la hoja en blanco si falla a medias."""
    valores = [headers] + (filas or [])
    if not filas:
        placeholder = [""] * len(headers)
        placeholder[0] = _ahora()
        placeholder[1] = "(sin registros aún — se llenan solos)"
        if len(placeholder) > 4:
            placeholder[4] = "Alessia escribe aquí cuando alguien pregunta o se inscribe"
        valores.append(placeholder)
    # 1) Escribir primero (si falla, queda lo anterior)
    service.spreadsheets().values().update(
        spreadsheetId=_sid(),
        range=f"{tab}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": valores},
    ).execute()
    # 2) Limpiar filas sobrantes debajo
    start = len(valores) + 1
    try:
        service.spreadsheets().values().clear(
            spreadsheetId=_sid(),
            range=f"{tab}!A{start}:Z2000",
        ).execute()
    except Exception as e:
        logger.debug("Clear sobrantes %s: %s", tab, e)
    tid = _sheet_ids(service).get(tab)
    if tid is not None:
        try:
            service.spreadsheets().batchUpdate(
                spreadsheetId=_sid(),
                body={
                    "requests": [
                        _paint(
                            tid, 0, 1, 0, len(headers), AZUL, bold=True, white_text=True
                        ),
                        {
                            "updateSheetProperties": {
                                "properties": {
                                    "sheetId": tid,
                                    "gridProperties": {"frozenRowCount": 1},
                                },
                                "fields": "gridProperties.frozenRowCount",
                            }
                        },
                    ]
                },
            ).execute()
        except Exception as e:
            logger.debug("Formato tabla %s: %s", tab, e)


def _recolectar_inscritos_desde_fuentes(service) -> list[list]:
    """Copia inscripciones del taller heridas desde la pestaña Inscripciones."""
    filas: list[list] = []
    vistos: set[str] = set()
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=_sid(), range="Inscripciones!A:F")
            .execute()
        )
        for row in result.get("values", [])[1:]:
            if len(row) < 5:
                continue
            taller = row[4] if len(row) > 4 else ""
            if not es_taller_heridas(taller):
                continue
            tel = row[2] if len(row) > 2 else ""
            key = _norm_tel(tel)
            if key and key in vistos:
                continue
            if key:
                vistos.add(key)
            modalidad = "Por confirmar"
            notas = f"Taller: {taller}"
            filas.append(
                [
                    row[0] if row else _ahora(),
                    row[1] if len(row) > 1 else "Sin nombre",
                    tel,
                    row[3] if len(row) > 3 else "No proporcionado",
                    modalidad,
                    (row[5] if len(row) > 5 else "PENDIENTE") or "PENDIENTE",
                    "",
                    "Inscripciones (sync)",
                    notas,
                ]
            )
    except Exception as e:
        logger.warning("Backfill inscritos heridas: %s", e)
    return filas


def _recolectar_interesados_desde_fuentes(service) -> list[list]:
    """Lista_Espera + FAQ relacionadas al taller heridas."""
    filas: list[list] = []
    vistos: set[str] = set()

    def _add(fecha, nombre, tel, consulta, fuente, estado, notas=""):
        key = _norm_tel(tel) or f"{nombre}:{consulta[:40]}"
        if key in vistos:
            return
        vistos.add(key)
        filas.append(
            [
                fecha or _ahora(),
                nombre or "Sin nombre",
                tel or "",
                (consulta or "Consulta taller heridas")[:500],
                fuente,
                estado,
                notas,
            ]
        )

    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=_sid(), range="Lista_Espera!A:F")
            .execute()
        )
        for row in result.get("values", [])[1:]:
            if len(row) < 4:
                continue
            blob = " ".join(str(c) for c in row).lower()
            if not any(
                x in blob
                for x in (
                    "herida",
                    "sanando",
                    "historia",
                    "niño",
                    "nino",
                )
            ):
                continue
            _add(
                row[0] if row else _ahora(),
                row[1] if len(row) > 1 else "",
                row[2] if len(row) > 2 else "",
                row[4] if len(row) > 4 else (row[3] if len(row) > 3 else "Interés taller"),
                "Lista_Espera",
                row[5] if len(row) > 5 else "Interesado",
                row[3] if len(row) > 3 else "",
            )
    except Exception as e:
        logger.warning("Backfill interesados Lista_Espera: %s", e)

    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=_sid(), range="FAQ_Pacientes!A:G")
            .execute()
        )
        for row in result.get("values", [])[1:]:
            if not row:
                continue
            preg = str(row[0] or "")
            if not es_taller_heridas(preg) and "herida" not in preg.lower():
                continue
            tel = row[6] if len(row) > 6 else ""
            _add(
                row[2] if len(row) > 2 else _ahora(),
                "Consulta FAQ",
                tel,
                preg,
                "FAQ_Pacientes",
                "Preguntando",
                f"Veces: {row[1] if len(row) > 1 else 1}",
            )
    except Exception as e:
        logger.debug("Backfill FAQ heridas: %s", e)

    return filas


def sincronizar_heridas_completo() -> dict:
    """
    Rellena Heridas_Inscritos / Heridas_Interesados desde fuentes existentes
    y regenera Heridas_Cupo (barra 0–100 + gráficas).
    Primero pinta el cupo (para que nunca quede en blanco si falla el resto).
    """
    if not _sid():
        raise RuntimeError("ID_HOJA_CALCULO vacío")
    service = get_sheets_service()
    _asegurar_tab(service, TAB_INSCRITOS, HEADERS_INSCRITOS)
    _asegurar_tab(service, TAB_INTERESADOS, HEADERS_INTERESADOS)
    _asegurar_tab(service, TAB_CUPO)

    # 1) Cupo visible de inmediato
    try:
        url = actualizar_dashboard_heridas()
    except Exception as e:
        logger.warning("Dashboard heridas inicial: %s", e)
        url = url_hoja_heridas()

    inscritos = _recolectar_inscritos_desde_fuentes(service)
    try:
        existentes = _leer_inscritos(service)
        vistos = {_norm_tel(r[2]) for r in inscritos if len(r) > 2}
        for r in existentes:
            if len(r) < 3:
                continue
            if (r[1] or "").startswith("(sin registros"):
                continue
            key = _norm_tel(r[2])
            if key and key not in vistos:
                inscritos.append(r)
                vistos.add(key)
    except Exception:
        pass

    interesados = _recolectar_interesados_desde_fuentes(service)
    try:
        existentes_i = _leer_interesados(service)
        vistos_i = {_norm_tel(r[2]) for r in interesados if len(r) > 2}
        for r in existentes_i:
            if len(r) < 3:
                continue
            if (r[1] or "").startswith("(sin registros"):
                continue
            key = _norm_tel(r[2]) if len(r) > 2 else ""
            if key and key not in vistos_i:
                interesados.append(r)
                vistos_i.add(key)
            elif not key and r not in interesados:
                interesados.append(r)
    except Exception:
        pass

    _escribir_tabla(service, TAB_INSCRITOS, HEADERS_INSCRITOS, inscritos)
    _escribir_tabla(service, TAB_INTERESADOS, HEADERS_INTERESADOS, interesados)
    try:
        url = actualizar_dashboard_heridas()
    except Exception as e:
        logger.warning("Dashboard heridas final: %s", e)
    out = {
        "inscritos": len(inscritos),
        "interesados": len(interesados),
        "url": url,
        "cupo_presencial_meta": CUPO_PRESENCIAL,
    }
    logger.info("Sync heridas completo: %s", out)
    try:
        storage.guardar_app_config("heridas_sync_ok", _ahora())
        storage.guardar_app_config("heridas_sync_error", "")
        storage.guardar_app_config("heridas_sync_detalle", str(out)[:800])
    except Exception:
        pass
    return out


def _paint(sheet_id, r0, r1, c0, c1, bg, *, bold=False, white_text=False):
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


def _norm_tel(telefono: str) -> str:
    return re.sub(r"\D", "", telefono or "")[-10:]


def _es_presencial(modalidad: str) -> bool:
    m = (modalidad or "").lower()
    if "online" in m or "en línea" in m or "en linea" in m or "zoom" in m:
        if "presencial" in m:
            return True  # híbrido: cuenta para cupo presencial si lo menciona
        return False
    # vacío / por confirmar / presencial → ocupa cupo presencial
    return True


def _leer_inscritos(service) -> list[list]:
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=_sid(), range=f"{TAB_INSCRITOS}!A2:I500")
        .execute()
    )
    return result.get("values", []) or []


def _leer_interesados(service) -> list[list]:
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=_sid(), range=f"{TAB_INTERESADOS}!A2:G500")
        .execute()
    )
    return result.get("values", []) or []


def _quitar_charts(service, sheet_id: int) -> None:
    meta = service.spreadsheets().get(
        spreadsheetId=_sid(), fields="sheets(properties,charts)"
    ).execute()
    reqs = []
    for s in meta.get("sheets", []):
        if s.get("properties", {}).get("sheetId") != sheet_id:
            continue
        for chart in s.get("charts") or []:
            cid = chart.get("chartId")
            if cid is not None:
                reqs.append({"deleteEmbeddedObject": {"objectId": cid}})
    if reqs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=_sid(), body={"requests": reqs}
        ).execute()


def actualizar_dashboard_heridas() -> str:
    """Reconstruye Heridas_Cupo: KPIs, barra 0–100, tablas resumen y gráficas."""
    if not _sid():
        return ""
    service = get_sheets_service()
    asegurar_hoja_heridas()
    cupo_id = _asegurar_tab(service, TAB_CUPO)
    inscritos = [
        r
        for r in _leer_inscritos(service)
        if len(r) > 1 and not str(r[1]).startswith("(sin registros")
    ]
    interesados = [
        r
        for r in _leer_interesados(service)
        if len(r) > 1 and not str(r[1]).startswith("(sin registros")
    ]

    n_total = len(inscritos)
    n_pres = sum(1 for r in inscritos if _es_presencial(r[4] if len(r) > 4 else ""))
    n_online = n_total - n_pres
    n_pagado = sum(
        1 for r in inscritos if len(r) > 5 and str(r[5]).upper() == "PAGADO"
    )
    n_pend = sum(
        1 for r in inscritos if len(r) > 5 and str(r[5]).upper() == "PENDIENTE"
    )
    n_interes = len(interesados)
    libres = max(0, CUPO_PRESENCIAL - n_pres)
    pct = min(100.0, (n_pres / CUPO_PRESENCIAL) * 100.0) if CUPO_PRESENCIAL else 0.0
    llenas = int(round(pct / (100 / BARRA_CELDAS)))
    llenas = max(0, min(BARRA_CELDAS, llenas))

    # Datos para gráficas (tabla auxiliar)
    # A20+: cupo chart | D20+: pago chart | G20+: interesados
    grid: list[list] = [[""] * 12 for _ in range(40)]

    def put(r, c, v):
        grid[r][c] = v

    put(0, 0, "TALLER: Sanando tus heridas del pasado — Panel de cupo e inscritos")
    put(1, 0, f"Actualizado: {_ahora()} (hora México)")
    put(1, 4, "Meta presencial")
    put(1, 5, CUPO_PRESENCIAL)

    put(3, 0, "INDICADOR DE CARGA PRESENCIAL (0 = vacío · 100 = lleno)")
    put(4, 0, "Inscritos presencial")
    put(4, 1, n_pres)
    put(5, 0, "Lugares libres")
    put(5, 1, libres)
    put(6, 0, "% llenado")
    put(6, 1, round(pct, 1))
    put(6, 2, "%")

    put(8, 0, "Línea de carga 0 → 100")
    put(9, 0, "0%")
    # barra en fila 10, columnas A..T
    for i in range(BARRA_CELDAS):
        put(10, i, "█" if i < llenas else "·")
    put(9, BARRA_CELDAS - 1, "100%")
    put(11, 0, f"{n_pres} / {CUPO_PRESENCIAL} lugares presencial")

    put(13, 0, "RESUMEN")
    put(14, 0, "Métrica")
    put(14, 1, "Cantidad")
    resumen = [
        ("Inscritos totales", n_total),
        ("Presencial (cupo)", n_pres),
        ("Online", n_online),
        ("Pagados", n_pagado),
        ("Pendientes de pago", n_pend),
        ("Interesados / preguntando", n_interes),
        ("Libres presencial", libres),
    ]
    for i, (k, v) in enumerate(resumen):
        put(15 + i, 0, k)
        put(15 + i, 1, v)

    # Datos gráfica cupo (pie)
    put(14, 3, "Cupo presencial")
    put(14, 4, "Personas")
    put(15, 3, "Ocupados")
    put(15, 4, n_pres)
    put(16, 3, "Libres")
    put(16, 4, libres)

    # Datos gráfica pagos
    put(14, 6, "Estatus pago")
    put(14, 7, "Cantidad")
    put(15, 6, "PAGADO")
    put(15, 7, n_pagado)
    put(16, 6, "PENDIENTE")
    put(16, 7, n_pend)
    put(17, 6, "Otros")
    put(17, 7, max(0, n_total - n_pagado - n_pend))

    # Datos interesados
    put(14, 9, "Embudo")
    put(14, 10, "Cantidad")
    put(15, 9, "Interesados")
    put(15, 10, n_interes)
    put(16, 9, "Inscritos")
    put(16, 10, n_total)

    put(24, 0, "Ver tablas detalladas → pestañas Heridas_Inscritos y Heridas_Interesados")
    put(
        25,
        0,
        "Este panel vive en el mismo Google Sheet de Alessia (Drive de la clínica).",
    )

    service.spreadsheets().values().update(
        spreadsheetId=_sid(),
        range=f"{TAB_CUPO}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": grid},
    ).execute()
    try:
        service.spreadsheets().values().clear(
            spreadsheetId=_sid(), range=f"{TAB_CUPO}!A{len(grid)+1}:L200"
        ).execute()
    except Exception:
        pass

    # Formato + barra de color
    reqs = [
        _paint(cupo_id, 0, 1, 0, 8, AZUL, bold=True, white_text=True),
        _paint(cupo_id, 3, 4, 0, 6, ROJO, bold=True, white_text=True),
        _paint(cupo_id, 8, 9, 0, 6, AZUL, bold=True, white_text=True),
        _paint(cupo_id, 13, 14, 0, 2, VERDE, bold=True, white_text=True),
        _paint(cupo_id, 14, 15, 0, 2, CREMA, bold=True),
        _paint(cupo_id, 14, 15, 3, 5, CREMA, bold=True),
        _paint(cupo_id, 14, 15, 6, 8, CREMA, bold=True),
        _paint(cupo_id, 14, 15, 9, 11, CREMA, bold=True),
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": cupo_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]
    for i in range(BARRA_CELDAS):
        bg = VERDE if i < llenas else GRIS
        if pct >= 90 and i < llenas:
            bg = ROJO
        elif pct >= 70 and i < llenas:
            bg = NARANJA
        reqs.append(_paint(cupo_id, 10, 11, i, i + 1, bg, bold=True, white_text=i < llenas))

    service.spreadsheets().batchUpdate(
        spreadsheetId=_sid(), body={"requests": reqs}
    ).execute()

    charts = [
        {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Cupo presencial (ocupados vs libres)",
                        "pieChart": {
                            "legendPosition": "RIGHT_LEGEND",
                            "domain": {
                                "sourceRange": {
                                    "sources": [
                                        {
                                            "sheetId": cupo_id,
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
                                            "sheetId": cupo_id,
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
                                "sheetId": cupo_id,
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
                        "title": "Pagos de inscritos",
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
                                                    "sheetId": cupo_id,
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
                                                    "sheetId": cupo_id,
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
                                "sheetId": cupo_id,
                                "rowIndex": 16,
                                "columnIndex": 3,
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
                        "title": "Embudo: interesados → inscritos",
                        "basicChart": {
                            "chartType": "BAR",
                            "legendPosition": "NO_LEGEND",
                            "headerCount": 1,
                            "domains": [
                                {
                                    "domain": {
                                        "sourceRange": {
                                            "sources": [
                                                {
                                                    "sheetId": cupo_id,
                                                    "startRowIndex": 14,
                                                    "endRowIndex": 17,
                                                    "startColumnIndex": 9,
                                                    "endColumnIndex": 10,
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
                                                    "sheetId": cupo_id,
                                                    "startRowIndex": 14,
                                                    "endRowIndex": 17,
                                                    "startColumnIndex": 10,
                                                    "endColumnIndex": 11,
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
                                "sheetId": cupo_id,
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
    try:
        _quitar_charts(service, cupo_id)
        service.spreadsheets().batchUpdate(
            spreadsheetId=_sid(), body={"requests": charts}
        ).execute()
    except Exception as e:
        logger.warning("Gráficas heridas (no bloqueante): %s", e)

    # Formato tabla de inscritos / interesados (cabeceras)
    for titulo, headers in (
        (TAB_INSCRITOS, HEADERS_INSCRITOS),
        (TAB_INTERESADOS, HEADERS_INTERESADOS),
    ):
        tid = _asegurar_tab(service, titulo, headers)
        service.spreadsheets().batchUpdate(
            spreadsheetId=_sid(),
            body={
                "requests": [
                    _paint(tid, 0, 1, 0, len(headers), AZUL, bold=True, white_text=True),
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": tid,
                                "gridProperties": {"frozenRowCount": 1},
                            },
                            "fields": "gridProperties.frozenRowCount",
                        }
                    },
                ]
            },
        ).execute()

    url = f"https://docs.google.com/spreadsheets/d/{_sid()}/edit#gid={cupo_id}"
    storage.guardar_app_config("url_hoja_heridas", url)
    storage.guardar_app_config("id_hoja_heridas", _sid())
    logger.info("Dashboard heridas OK: %s (presencial %s/%s)", url, n_pres, CUPO_PRESENCIAL)
    return url


def asegurar_hoja_heridas(*, forzar_crear: bool = False) -> str:
    """Asegura pestañas en el Sheet principal y refresca el panel de cupo."""
    if not _sid():
        raise RuntimeError("ID_HOJA_CALCULO vacío")
    service = get_sheets_service()
    _asegurar_tab(service, TAB_INSCRITOS, HEADERS_INSCRITOS)
    _asegurar_tab(service, TAB_INTERESADOS, HEADERS_INTERESADOS)
    _asegurar_tab(service, TAB_CUPO)
    # No recursar: dashboard se llama aparte; aquí solo tabs
    if forzar_crear:
        actualizar_dashboard_heridas()
    return _sid()


def _append_fila(tab: str, fila: list, *, refrescar_cupo: bool = False) -> bool:
    """Append fila. NO regenera Heridas_Cupo en el hot path (tumba WhatsApp)."""
    try:
        asegurar_hoja_heridas()
        service = get_sheets_service()
        service.spreadsheets().values().append(
            spreadsheetId=_sid(),
            range=f"{tab}!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [fila]},
        ).execute()
        if refrescar_cupo:
            try:
                actualizar_dashboard_heridas()
            except Exception as e:
                logger.warning("Dashboard heridas tras append: %s", e)
        return True
    except Exception as e:
        logger.error("Error escribiendo %s heridas: %s", tab, e)
        return False


def _en_background(nombre: str, fn, *args, **kwargs) -> None:
    """Sheets fuera del webhook/cola: no bloquea WhatsApp si Google va lento."""

    def _run():
        try:
            fn(*args, **kwargs)
        except Exception as e:
            logger.warning("BG heridas %s: %s", nombre, e)

    threading.Thread(target=_run, daemon=True, name=f"heridas-{nombre}").start()


def registrar_interesado_heridas_async(**kwargs) -> None:
    _en_background("interesado", registrar_interesado_heridas, **kwargs)


def registrar_inscrito_heridas_async(**kwargs) -> None:
    _en_background("inscrito", registrar_inscrito_heridas, **kwargs)


def marcar_interesado_como_inscrito_async(telefono: str) -> None:
    _en_background("marcar_inscrito", marcar_interesado_como_inscrito, telefono)


def _ya_inscrito_reciente(telefono: str) -> bool:
    try:
        if not _sid():
            return False
        service = get_sheets_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=_sid(), range=f"{TAB_INSCRITOS}!C2:C200")
            .execute()
        )
        target = _norm_tel(telefono)
        for row in result.get("values", []):
            if row and target and target in re.sub(r"\D", "", row[0]):
                return True
    except Exception as e:
        logger.debug("Dedup inscritos heridas: %s", e)
    return False


def _interesado_fila(telefono: str) -> int | None:
    try:
        if not _sid():
            return None
        service = get_sheets_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=_sid(), range=f"{TAB_INTERESADOS}!A2:F500")
            .execute()
        )
        target = _norm_tel(telefono)
        for i, row in enumerate(result.get("values", [])):
            if len(row) < 3:
                continue
            if target and target in re.sub(r"\D", "", row[2]):
                return i + 2
    except Exception as e:
        logger.debug("Buscar interesado heridas: %s", e)
    return None


def registrar_inscrito_heridas(
    *,
    nombre: str,
    telefono: str,
    correo: str = "",
    modalidad: str = "",
    estatus_pago: str = "PENDIENTE",
    monto: str = "",
    fuente: str = "WhatsApp Alessia",
    notas: str = "",
) -> bool:
    if _ya_inscrito_reciente(telefono):
        return actualizar_estatus_inscrito(telefono, estatus_pago, monto=monto)
    return _append_fila(
        TAB_INSCRITOS,
        [
            _ahora(),
            (nombre or "").strip() or "Sin nombre",
            telefono,
            (correo or "").strip() or "No proporcionado",
            (modalidad or "").strip() or "Por confirmar",
            estatus_pago,
            monto,
            fuente,
            notas,
        ],
    )


def actualizar_estatus_inscrito(
    telefono: str, estatus: str, *, monto: str = ""
) -> bool:
    try:
        asegurar_hoja_heridas()
        service = get_sheets_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=_sid(), range=f"{TAB_INSCRITOS}!A2:I500")
            .execute()
        )
        target = _norm_tel(telefono)
        rows = result.get("values", [])
        for i, row in enumerate(rows):
            if len(row) < 3:
                continue
            if target and target in re.sub(r"\D", "", row[2]):
                fila = i + 2
                service.spreadsheets().values().update(
                    spreadsheetId=_sid(),
                    range=f"{TAB_INSCRITOS}!F{fila}:G{fila}",
                    valueInputOption="USER_ENTERED",
                    body={
                        "values": [
                            [estatus, monto or (row[6] if len(row) > 6 else "")]
                        ]
                    },
                ).execute()
                return True
        return registrar_inscrito_heridas(
            nombre=storage.primer_nombre(telefono) or "Paciente",
            telefono=telefono,
            estatus_pago=estatus,
            monto=monto,
            notas="Alta al confirmar pago",
        )
    except Exception as e:
        logger.error("Error actualizando inscrito heridas: %s", e)
        return False


def registrar_interesado_heridas(
    *,
    telefono: str,
    consulta: str = "",
    nombre: str = "",
    fuente: str = "WhatsApp consulta",
    estado: str = "Preguntando",
    notas: str = "",
) -> bool:
    nombre_n = (nombre or "").strip() or storage.primer_nombre(telefono) or "Sin nombre"
    consulta_n = (consulta or "").strip()[:500]
    fila_existente = _interesado_fila(telefono)
    if fila_existente:
        try:
            asegurar_hoja_heridas()
            service = get_sheets_service()
            service.spreadsheets().values().update(
                spreadsheetId=_sid(),
                range=f"{TAB_INTERESADOS}!A{fila_existente}:G{fila_existente}",
                valueInputOption="USER_ENTERED",
                body={
                    "values": [
                        [
                            _ahora(),
                            nombre_n,
                            telefono,
                            consulta_n or "Consulta taller heridas",
                            fuente,
                            estado,
                            notas,
                        ]
                    ]
                },
            ).execute()
            # No regenerar Heridas_Cupo aquí: bloquearía WhatsApp. Usar Modo Pro sync.
            return True
        except Exception as e:
            logger.error("Error actualizando interesado heridas: %s", e)
            return False
    return _append_fila(
        TAB_INTERESADOS,
        [
            _ahora(),
            nombre_n,
            telefono,
            consulta_n or "Consulta taller heridas",
            fuente,
            estado,
            notas,
        ],
    )


def marcar_interesado_como_inscrito(telefono: str) -> None:
    fila = _interesado_fila(telefono)
    if not fila:
        return
    try:
        service = get_sheets_service()
        service.spreadsheets().values().update(
            spreadsheetId=_sid(),
            range=f"{TAB_INTERESADOS}!F{fila}",
            valueInputOption="USER_ENTERED",
            body={"values": [["Inscrito"]]},
        ).execute()
    except Exception as e:
        logger.debug("Marcar interesado inscrito: %s", e)


def sincronizar_panel_heridas() -> str:
    """
    Modo Pro: actualiza tablas heridas. NO regenera gráficas aquí:
    eso tumba el worker en basic-xs justo después del sync.
    Gráficas: /ops/sync-heridas?completo=1
    """
    try:
        out = sincronizar_heridas_datos()
        storage.guardar_app_config("heridas_sync_ok", _ahora())
        storage.guardar_app_config("heridas_sync_error", "")
        storage.guardar_app_config("heridas_sync_detalle", str(out)[:800])
        return (
            "ÉXITO: Panel del taller heridas actualizado en Google Sheets.\n"
            f"• Inscritos: {out.get('inscritos', 0)}\n"
            f"• Interesados: {out.get('interesados', 0)}\n"
            f"• Meta cupo presencial: {out.get('cupo_presencial_meta', CUPO_PRESENCIAL)}\n"
            f"• Link: {out.get('url') or url_hoja_heridas()}\n"
            "Abre *Heridas_Cupo*, *Heridas_Inscritos* y *Heridas_Interesados*.\n"
            "(Las gráficas de cupo se actualizan con sync completo en ops, no en WhatsApp.)"
        )
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        storage.guardar_app_config("heridas_sync_error", msg[:800])
        logger.exception("sincronizar_panel_heridas")
        return (
            f"ERROR: No pude actualizar la hoja heridas ({msg}). "
            "Revisa que la cuenta de servicio tenga acceso de editor al Sheet de Alessia."
        )


def sincronizar_heridas_datos() -> dict:
    """Escribe Inscritos/Interesados y un cupo simple — sin recrear gráficas."""
    if not _sid():
        raise RuntimeError("ID_HOJA_CALCULO vacío")
    service = get_sheets_service()
    _asegurar_tab(service, TAB_INSCRITOS, HEADERS_INSCRITOS)
    _asegurar_tab(service, TAB_INTERESADOS, HEADERS_INTERESADOS)
    _asegurar_tab(service, TAB_CUPO)

    inscritos = _recolectar_inscritos_desde_fuentes(service)
    try:
        existentes = _leer_inscritos(service)
        vistos = {_norm_tel(r[2]) for r in inscritos if len(r) > 2}
        for r in existentes:
            if len(r) < 3:
                continue
            if (r[1] or "").startswith("(sin registros"):
                continue
            key = _norm_tel(r[2])
            if key and key not in vistos:
                inscritos.append(r)
                vistos.add(key)
    except Exception:
        pass

    interesados = _recolectar_interesados_desde_fuentes(service)
    try:
        existentes_i = _leer_interesados(service)
        vistos_i = {_norm_tel(r[2]) for r in interesados if len(r) > 2}
        for r in existentes_i:
            if len(r) < 3:
                continue
            if (r[1] or "").startswith("(sin registros"):
                continue
            key = _norm_tel(r[2]) if len(r) > 2 else ""
            if key and key not in vistos_i:
                interesados.append(r)
                vistos_i.add(key)
            elif not key and r not in interesados:
                interesados.append(r)
    except Exception:
        pass

    _escribir_tabla(service, TAB_INSCRITOS, HEADERS_INSCRITOS, inscritos)
    _escribir_tabla(service, TAB_INTERESADOS, HEADERS_INTERESADOS, interesados)

    n_pres = sum(
        1
        for r in inscritos
        if len(r) > 1
        and not str(r[1]).startswith("(sin registros")
        and _es_presencial(r[4] if len(r) > 4 else "")
    )
    libres = max(0, CUPO_PRESENCIAL - n_pres)
    resumen = [
        ["TALLER: Sanando tus heridas del pasado — datos"],
        [f"Actualizado: {_ahora()} (hora México)"],
        [],
        ["Inscritos totales", len(inscritos)],
        ["Presencial (cupo)", n_pres],
        ["Libres presencial", libres],
        ["Interesados", len(interesados)],
        ["Meta cupo", CUPO_PRESENCIAL],
        [],
        ["Las gráficas se actualizan en segundo plano tras el sync."],
        [f"Link: {url_hoja_heridas()}"],
    ]
    service.spreadsheets().values().update(
        spreadsheetId=_sid(),
        range=f"{TAB_CUPO}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": resumen},
    ).execute()

    out = {
        "inscritos": len(
            [r for r in inscritos if len(r) > 1 and not str(r[1]).startswith("(sin registros")]
        ),
        "interesados": len(
            [
                r
                for r in interesados
                if len(r) > 1 and not str(r[1]).startswith("(sin registros")
            ]
        ),
        "url": url_hoja_heridas(),
        "cupo_presencial_meta": CUPO_PRESENCIAL,
    }
    logger.info("Sync heridas datos (rápido): %s", out)
    return out


def es_pedido_sync_panel_heridas(texto: str) -> bool:
    """Detecta pedidos naturales de sincronizar el panel heridas en Sheets."""
    if not texto:
        return False
    n = unicodedata.normalize("NFD", texto.lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    n = re.sub(r"\s+", " ", n).strip()
    if "herida" not in n and "heridas_cupo" not in n.replace(" ", "_"):
        return False
    if re.search(
        r"(sincroniz\w*|actualiz\w*|llen\w*|rellen\w*|refresc\w*|sync)\w*.{0,40}"
        r"(hoja|sheet|panel|cupo|inscritos|interesados|pestana)",
        n,
    ):
        return True
    if re.search(r"(hoja|panel|sheet).{0,30}heridas", n) and re.search(
        r"(sincroniz|actualiz|llen|rellen|refresc|sync)", n
    ):
        return True
    if re.search(r"\b(sync|sincroniza|sincronizar)\s+heridas\b", n):
        return True
    return False


def _clave_sync_pendiente(telefono: str) -> str:
    return f"heridas_sync_pendiente_{(telefono or '').strip()}"


def marcar_sync_heridas_pendiente(telefono: str) -> None:
    storage.guardar_app_config(_clave_sync_pendiente(telefono), _ahora())


def limpiar_sync_heridas_pendiente(telefono: str) -> None:
    storage.guardar_app_config(_clave_sync_pendiente(telefono), "")


def _parse_ts_mexico(valor: str) -> datetime | None:
    raw = (valor or "").strip()
    if not raw:
        return None
    try:
        naive = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
        return ZONA.localize(naive)
    except Exception:
        return None


def sync_heridas_pendiente_expirado(telefono: str) -> bool:
    """True si el flag pendiente es viejo (deploy/hang); lo limpia."""
    pendiente = storage.obtener_app_config(_clave_sync_pendiente(telefono), "")
    if not pendiente:
        return False
    ts = _parse_ts_mexico(pendiente)
    if ts is None:
        limpiar_sync_heridas_pendiente(telefono)
        return True
    if datetime.now(ZONA) - ts > timedelta(minutes=SYNC_PENDIENTE_MAX_MIN):
        limpiar_sync_heridas_pendiente(telefono)
        logger.info(
            "Sync heridas pendiente expirado (%s min) tel …%s",
            SYNC_PENDIENTE_MAX_MIN,
            (telefono or "")[-4:],
        )
        return True
    return False


def es_pregunta_estado_sync_heridas(texto: str) -> bool:
    """True si preguntan si ya terminó el sync (ej. «ya quedó?»)."""
    if not texto:
        return False
    n = unicodedata.normalize("NFD", texto.lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    n = re.sub(r"\s+", " ", n).strip()
    if len(n) > 48:
        return False
    pistas = (
        "ya quedo",
        "ya quedo?",
        "ya quedo ?",
        "ya esta",
        "ya esta?",
        "quedo listo",
        "quedo?",
        "listo?",
        "termino",
        "termino?",
        "avance",
        "como va",
        "como va la hoja",
        "ya sincronizo",
        "ya actualizo",
    )
    return any(p in n for p in pistas)


def responder_estado_sync_heridas(telefono: str) -> str | None:
    """Respuesta corta al preguntar por el sync reciente; None si no hay rastro."""
    if sync_heridas_pendiente_expirado(telefono):
        ok = storage.obtener_app_config("heridas_sync_ok", "")
        err = storage.obtener_app_config("heridas_sync_error", "")
        if err:
            return f"El último sync falló: {err}"
        if ok:
            return (
                f"El sync ya no está en proceso. El último OK fue a las {ok}. "
                "Si no ves los datos, vuelve a escribir *sincroniza la hoja de heridas*."
            )
        return (
            "Ese sync se quedó colgado o el servidor reinició. "
            "Vuelve a escribir *sincroniza la hoja de heridas*."
        )
    pendiente = storage.obtener_app_config(_clave_sync_pendiente(telefono), "")
    ok = storage.obtener_app_config("heridas_sync_ok", "")
    err = storage.obtener_app_config("heridas_sync_error", "")
    detalle = storage.obtener_app_config("heridas_sync_detalle", "")
    if pendiente:
        return (
            "Sigue en proceso… en cuanto termine te confirmo aquí. "
            "Si pasan más de un minuto, vuelve a escribir *sincroniza la hoja de heridas*."
        )
    if err:
        return f"El último sync falló: {err}"
    if ok:
        extra = f"\n{detalle}" if detalle else ""
        return f"Sí, el último sync quedó listo a las {ok}.{extra}"
    return None


def intentar_comando_sync_heridas(
    telefono: str,
    texto: str,
    *,
    requerir_modo_pro: bool = True,
) -> str | None:
    """
    Si el mensaje pide sync del panel heridas, ejecuta y devuelve respuesta.
    Por defecto solo con sesión Modo Pro activa.
    """
    if not es_pedido_sync_panel_heridas(texto):
        return None
    if requerir_modo_pro and not storage.sesion_equipo_activa(telefono):
        return None
    quien = (
        config.identificar_personal_inpulso(telefono)
        or storage.obtener_nombre_equipo_sesion(telefono)
        or "Equipo"
    )
    logger.info("Sync heridas por comando Modo Pro de %s (%s)", quien, telefono[-4:])
    marcar_sync_heridas_pendiente(telefono)
    try:
        resultado = sincronizar_panel_heridas()
        return f"Listo, *{quien}* ✨\n\n{resultado}"
    finally:
        limpiar_sync_heridas_pendiente(telefono)
