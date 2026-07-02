"""Sincroniza la pestaña Catalogo de Google Sheets con inpulso43.com."""
from __future__ import annotations

import logging

import config
from catalogo import CATALOGO_TAB, _filas_crudas_catalogo, invalidar_cache
from catalogo_web import _fila_taller, id_web_desde_texto, obtener_talleres_vigentes
from catalogo_web_live import cargar_talleres_publicados_web, invalidar_cache_web
from google_client import get_sheets_service

logger = logging.getLogger(__name__)


def _fila_sheet_por_id_web(rows: list[list], id_web: str) -> int | None:
    for i, row in enumerate(rows):
        if len(row) < 3:
            continue
        if (row[1] if len(row) > 1 else "").strip().lower() != "taller":
            continue
        if id_web_desde_texto(row[2]) == id_web:
            return i + 2
    return None


def sincronizar_catalogo_desde_web(*, forzar_lectura_web: bool = True) -> dict:
    """
    Actualiza filas de talleres en la hoja Catalogo según la web vigente.
    Desactiva filas viejas del mismo taller (mismo id_web, otro nombre).
    """
    if not config.ID_HOJA_CALCULO:
        return {"ok": False, "error": "ID_HOJA_CALCULO vacío"}

    if forzar_lectura_web:
        invalidar_cache_web()
        cargar_talleres_publicados_web(forzar=True)

    talleres = obtener_talleres_vigentes()
    service = get_sheets_service()
    rows = _filas_crudas_catalogo()

    actualizados = 0
    agregados = 0
    desactivados = 0
    web_ids = {t["id_web"] for t in talleres}
    fila_principal_por_id: dict[str, int] = {}

    for taller in talleres:
        fila_vals = _fila_taller(taller)
        fila_num = _fila_sheet_por_id_web(rows, taller["id_web"])
        if fila_num:
            fila_principal_por_id[taller["id_web"]] = fila_num
            service.spreadsheets().values().update(
                spreadsheetId=config.ID_HOJA_CALCULO,
                range=f"{CATALOGO_TAB}!A{fila_num}:J{fila_num}",
                valueInputOption="USER_ENTERED",
                body={"values": [fila_vals]},
            ).execute()
            actualizados += 1
        else:
            service.spreadsheets().values().append(
                spreadsheetId=config.ID_HOJA_CALCULO,
                range=f"{CATALOGO_TAB}!A:J",
                valueInputOption="USER_ENTERED",
                body={"values": [fila_vals]},
            ).execute()
            agregados += 1

    for i, row in enumerate(rows):
        if len(row) < 3:
            continue
        if (row[1] if len(row) > 1 else "").strip().lower() != "taller":
            continue
        nombre = row[2].strip()
        tid = id_web_desde_texto(nombre)
        if not tid or tid not in web_ids:
            continue
        fila_num = i + 2
        if fila_principal_por_id.get(tid) == fila_num:
            continue
        activo = (row[9] if len(row) > 9 else "SI").strip().upper()
        if activo in ("NO", "N"):
            continue
        service.spreadsheets().values().update(
            spreadsheetId=config.ID_HOJA_CALCULO,
            range=f"{CATALOGO_TAB}!J{fila_num}",
            valueInputOption="USER_ENTERED",
            body={"values": [["NO"]]},
        ).execute()
        desactivados += 1

    invalidar_cache()
    resultado = {
        "ok": True,
        "actualizados": actualizados,
        "agregados": agregados,
        "desactivados": desactivados,
        "talleres": len(talleres),
    }
    logger.info("Catálogo sincronizado con web: %s", resultado)
    return resultado
