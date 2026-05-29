"""Catálogo de talleres y servicios desde Google Sheets (Drive)."""
import json
import logging
import time

import config
from google_client import get_sheets_service

logger = logging.getLogger(__name__)

CATALOGO_TAB = "Catalogo"
HEADERS = [
    "Terapeuta",
    "Tipo",
    "Nombre",
    "Fechas",
    "Horario",
    "Modalidad",
    "Precio",
    "Cupo",
    "Temario",
    "Activo",
]

_cache = {"rows": None, "ts": 0}
_CACHE_TTL = 300  # 5 minutos


def _leer_filas_catalogo() -> list[dict]:
    global _cache
    ahora = time.time()
    if _cache["rows"] is not None and ahora - _cache["ts"] < _CACHE_TTL:
        return _cache["rows"]

    if not config.ID_HOJA_CALCULO:
        return []

    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO,
            range=f"{CATALOGO_TAB}!A2:J",
        ).execute()
        rows_raw = result.get("values", [])
    except Exception as e:
        logger.warning("No se pudo leer hoja Catalogo: %s", e)
        return []

    filas = []
    for row in rows_raw:
        if len(row) < 3:
            continue
        activo = (row[9] if len(row) > 9 else "SI").strip().upper()
        if activo not in ("SI", "SÍ", "S", "YES", "1", "TRUE"):
            continue
        filas.append(
            {
                "terapeuta": row[0].strip() if len(row) > 0 else "",
                "tipo": row[1].strip().lower() if len(row) > 1 else "",
                "nombre": row[2].strip() if len(row) > 2 else "",
                "fechas": row[3].strip() if len(row) > 3 else "",
                "horario": row[4].strip() if len(row) > 4 else "",
                "modalidad": row[5].strip() if len(row) > 5 else "",
                "precio": row[6].strip() if len(row) > 6 else "",
                "cupo": row[7].strip() if len(row) > 7 else "",
                "temario": row[8].strip() if len(row) > 8 else "",
            }
        )

    _cache = {"rows": filas, "ts": ahora}
    return filas


def invalidar_cache():
    _cache["rows"] = None
    _cache["ts"] = 0


def consultar_catalogo_drive(especialista: str = "todos"):
    """
    Consulta talleres y servicios publicados por terapeutas en Google Sheets.
    Los terapeutas editan la hoja 'Catalogo' del archivo en Drive.
    """
    filas = _leer_filas_catalogo()
    if not filas:
        return (
            "INSTRUCCIÓN PARA LA IA: No hay catálogo en Drive todavía o la hoja "
            "'Catalogo' está vacía. Usa consultar_precios_y_servicios como respaldo."
        )

    esp_lower = especialista.lower()
    if esp_lower != "todos":
        filtradas = [
            f
            for f in filas
            if esp_lower in f["terapeuta"].lower() or esp_lower in f["nombre"].lower()
        ]
        if not filtradas:
            return (
                f"No encontré talleres o servicios de {especialista} en el catálogo de Drive."
            )
        return "Catálogo de Drive: " + json.dumps(filtradas, ensure_ascii=False)

    return "Catálogo completo de Drive: " + json.dumps(filas, ensure_ascii=False)


def obtener_cuentas_pago_texto() -> str:
    banorte = config.CUENTAS_OFICIALES["BANORTE"]
    banamex = config.CUENTAS_OFICIALES["BANAMEX"]
    return (
        f"BANORTE CLABE {banorte['clabe']} ({banorte['titular']}) | "
        f"BANAMEX CLABE {banamex['clabe']} ({banamex['titular']})"
    )
