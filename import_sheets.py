"""Importación única (solo lectura) de Google Sheets → SQLite. Sin sync continuo."""
from __future__ import annotations

import logging
import re
import threading

import config
import storage
from google_client import get_sheets_service

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_en_curso = False

PESTANAS = (
    ("Heridas_Inscritos", "A:I"),
    ("Heridas_Interesados", "A:G"),
    ("FAQ_Pacientes", "A:G"),
    ("Inscripciones", "A:F"),
    ("PagosCitas", "A:G"),
    ("Conocimiento", "A:G"),
    ("Lista_Espera", "A:F"),
)

_PLACEHOLDER = ("sin registros aún", "se llenan solos")


def _cel(row: list, i: int) -> str:
    if i >= len(row):
        return ""
    return str(row[i] or "").strip()


def _es_placeholder(row: list) -> bool:
    blob = " ".join(str(c).lower() for c in row)
    return any(p in blob for p in _PLACEHOLDER)


def _leer_rango(service, rango: str) -> list[list]:
    sid = (config.ID_HOJA_CALCULO or "").strip()
    if not sid:
        return []
    try:
        data = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sid, range=rango)
            .execute()
            .get("values", [])
        )
        return data or []
    except Exception as e:
        logger.warning("No se pudo leer %s: %s", rango, e)
        return []


def _fusionar_operativo(pestana: str, headers: list[str], filas: list[list]) -> None:
    h = [str(x).strip().lower() for x in headers]

    def col(*nombres: str) -> int:
        for n in nombres:
            if n in h:
                return h.index(n)
        return -1

    if pestana == "FAQ_Pacientes":
        i_p = col("pregunta")
        i_v = col("veces")
        i_u = col("ultima_vez", "última_vez")
        i_t = col("whatsapp")
        for row in filas:
            if _es_placeholder(row):
                continue
            pregunta = _cel(row, i_p if i_p >= 0 else 0)
            if not pregunta:
                continue
            veces = 1
            try:
                veces = int(float(_cel(row, i_v if i_v >= 0 else 1) or "1"))
            except ValueError:
                veces = 1
            storage.fusionar_pregunta_frecuente_import(
                pregunta,
                veces,
                _cel(row, i_u if i_u >= 0 else 2),
                _cel(row, i_t if i_t >= 0 else 6),
            )
        return

    if pestana == "Conocimiento":
        i_tema = col("tema")
        i_cont = col("contenido")
        i_keys = col("palabras_clave")
        i_quien = col("quien")
        i_act = col("activo")
        for row in filas:
            if _es_placeholder(row):
                continue
            if i_act >= 0 and _cel(row, i_act).lower() in ("0", "no", "false"):
                continue
            tema = _cel(row, i_tema if i_tema >= 0 else 1)
            contenido = _cel(row, i_cont if i_cont >= 0 else 2)
            if tema and contenido:
                storage.upsert_conocimiento_clinica(
                    tema,
                    contenido,
                    _cel(row, i_keys if i_keys >= 0 else 3),
                    _cel(row, i_quien if i_quien >= 0 else 4) or "import-sheets",
                )
        return

    i_tel = col("whatsapp", "teléfono", "telefono")
    i_nom = col("nombre")
    i_taller = col("taller", "consulta", "fuente")
    i_fecha = col("fecha", "fecha registro")
    if i_tel < 0:
        i_tel = 2 if pestana != "PagosCitas" else 1
    if i_nom < 0:
        i_nom = 2 if pestana == "PagosCitas" else 1

    for row in filas:
        if _es_placeholder(row):
            continue
        tel = re.sub(r"\D", "", _cel(row, i_tel))
        nombre = _cel(row, i_nom)
        if tel and len(tel) >= 10:
            storage.guardar_nombre_paciente(tel, nombre or tel)
        if pestana in ("Heridas_Interesados", "Heridas_Inscritos", "Inscripciones"):
            taller = _cel(row, i_taller if i_taller >= 0 else 4)
            if tel and len(tel) >= 10:
                origen = taller or pestana
                storage.registrar_interes_taller(
                    tel,
                    "heridas" if "herida" in pestana.lower() else (taller or "import"),
                    origen,
                    nombre,
                )


def ejecutar_importacion_sheets() -> dict:
    """Lee pestañas (GET values) y las copia a SQLite. No escribe al Sheet."""
    global _en_curso
    with _lock:
        if _en_curso:
            return {"ok": False, "estado": "en_curso"}
        _en_curso = True
    try:
        storage.guardar_app_config("sheets_import_estado", "en_curso")
        service = get_sheets_service()
        resumen: dict[str, int] = {}
        for pestana, cols in PESTANAS:
            crudo = _leer_rango(service, f"{pestana}!{cols}")
            if not crudo:
                resumen[pestana] = 0
                continue
            headers = [str(c).strip() for c in crudo[0]]
            filas = [list(r) for r in crudo[1:] if any(str(c).strip() for c in r)]
            n = storage.reemplazar_pestana_importada(pestana, headers, filas)
            _fusionar_operativo(pestana, headers, filas)
            resumen[pestana] = n
        storage.guardar_app_config("sheets_import_estado", "ok")
        storage.guardar_app_config(
            "sheets_import_resumen",
            ", ".join(f"{k}:{v}" for k, v in resumen.items()),
        )
        try:
            from db_backup import subir_sqlite_live

            subir_sqlite_live()
        except Exception as e:
            logger.warning("No se pudo guardar copia live: %s", e)
        return {"ok": True, "estado": "ok", "resumen": resumen}
    except Exception as e:
        logger.exception("Import Sheets")
        storage.guardar_app_config("sheets_import_estado", f"error: {e}"[:400])
        return {"ok": False, "estado": "error", "error": str(e)}
    finally:
        _en_curso = False


def lanzar_importacion_una_vez(*, forzar: bool = False) -> dict:
    estado = storage.obtener_app_config("sheets_import_estado", "")
    if estado == "ok" and not forzar:
        return {
            "ok": True,
            "estado": "ya_importado",
            "resumen": storage.obtener_app_config("sheets_import_resumen", ""),
        }
    if estado == "en_curso":
        return {"ok": True, "estado": "en_curso"}

    def _run():
        ejecutar_importacion_sheets()

    threading.Thread(target=_run, daemon=True, name="import-sheets-once").start()
    return {"ok": True, "estado": "lanzado"}
