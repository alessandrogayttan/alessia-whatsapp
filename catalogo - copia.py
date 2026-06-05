"""Catálogo de talleres y servicios desde Google Sheets (Drive)."""
import datetime
import json
import logging
import re
import time

import pytz

import config
from google_client import get_sheets_service

ZONA = pytz.timezone(config.ZONA_MEXICO)
MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

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


def _fechas_sesiones_taller(fechas_txt: str) -> list[datetime.date]:
    """Extrae fechas de sesiones desde texto tipo 'Lunes 1 y 8 de junio'."""
    if not fechas_txt:
        return []
    texto = fechas_txt.lower()
    mes = None
    for nombre, num in MESES_ES.items():
        if nombre in texto:
            mes = num
            break
    if not mes:
        return []
    dias = [int(d) for d in re.findall(r"\b(\d{1,2})\b", texto)]
    if not dias:
        return []
    hoy = datetime.datetime.now(ZONA).date()
    anio = hoy.year
    if mes < hoy.month or (mes == hoy.month and max(dias) < hoy.day):
        anio += 1
    fechas = []
    for dia in sorted(set(dias)):
        try:
            fechas.append(datetime.date(anio, mes, dia))
        except ValueError:
            continue
    return fechas


def estado_taller(fechas_txt: str) -> dict:
    """
    Calcula si un taller está por iniciar, en curso o finalizado.
    Devuelve estado, fechas y aviso listo para la IA.
    """
    sesiones = _fechas_sesiones_taller(fechas_txt)
    if not sesiones:
        return {
            "estado_taller": "desconocido",
            "aviso_estado": "",
            "sesiones": [],
        }

    hoy = datetime.datetime.now(ZONA).date()
    pasadas = [f for f in sesiones if f < hoy]
    futuras = [f for f in sesiones if f >= hoy]

    if not pasadas:
        prox = futuras[0]
        aviso = f"Aún no inicia. Primera sesión: {prox.strftime('%d/%m/%Y')}."
        return {
            "estado_taller": "por_iniciar",
            "aviso_estado": aviso,
            "sesiones": [f.isoformat() for f in sesiones],
            "proxima_sesion": prox.isoformat(),
        }

    if futuras:
        ultima_pasada = pasadas[-1]
        prox = futuras[0]
        aviso = (
            f"YA ESTÁ EN CURSO: la sesión del {ultima_pasada.strftime('%d/%m/%Y')} ya se realizó. "
            f"Próxima sesión: {prox.strftime('%d/%m/%Y')}."
        )
        return {
            "estado_taller": "en_curso",
            "aviso_estado": aviso,
            "sesiones": [f.isoformat() for f in sesiones],
            "proxima_sesion": prox.isoformat(),
        }

    ultima = pasadas[-1]
    aviso = f"Ya finalizó. Última sesión fue el {ultima.strftime('%d/%m/%Y')}."
    return {
        "estado_taller": "finalizado",
        "aviso_estado": aviso,
        "sesiones": [f.isoformat() for f in sesiones],
    }


def _enriquecer_fila_catalogo(fila: dict) -> dict:
    if fila.get("tipo") == "taller" and fila.get("fechas"):
        fila = {**fila, **estado_taller(fila["fechas"])}
    return fila


def _filas_crudas_catalogo() -> list[list]:
    if not config.ID_HOJA_CALCULO:
        return []
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{CATALOGO_TAB}!A2:J",
    ).execute()
    return result.get("values", [])


def listar_catalogo_terapeuta(terapeuta: str, incluir_inactivos: bool = False) -> list[dict]:
    terapeuta_lower = terapeuta.lower()
    filas = []
    for row in _filas_crudas_catalogo():
        if len(row) < 3:
            continue
        if terapeuta_lower not in row[0].lower():
            continue
        activo_raw = (row[9] if len(row) > 9 else "SI").strip().upper()
        activo = activo_raw in ("SI", "SÍ", "S", "YES", "1", "TRUE")
        if not incluir_inactivos and not activo:
            continue
        filas.append(
            {
                "terapeuta": row[0].strip(),
                "tipo": row[1].strip().lower() if len(row) > 1 else "",
                "nombre": row[2].strip() if len(row) > 2 else "",
                "fechas": row[3].strip() if len(row) > 3 else "",
                "horario": row[4].strip() if len(row) > 4 else "",
                "modalidad": row[5].strip() if len(row) > 5 else "",
                "precio": row[6].strip() if len(row) > 6 else "",
                "cupo": row[7].strip() if len(row) > 7 else "",
                "temario": row[8].strip() if len(row) > 8 else "",
                "activo": activo,
            }
        )
    return filas


def _buscar_fila_catalogo(terapeuta: str, nombre: str) -> int | None:
    terapeuta_lower = terapeuta.lower()
    nombre_lower = nombre.lower()
    for i, row in enumerate(_filas_crudas_catalogo()):
        if len(row) < 3:
            continue
        if terapeuta_lower in row[0].lower() and nombre_lower in row[2].lower():
            return i + 2  # fila en sheet (1-based, + header)
    return None


def agregar_entrada_catalogo(
    terapeuta: str,
    tipo: str,
    nombre: str,
    fechas: str = "",
    horario: str = "",
    modalidad: str = "Presencial",
    precio: str = "",
    cupo: str = "",
    temario: str = "",
    activo: str = "SI",
) -> tuple[bool, str]:
    if not config.ID_HOJA_CALCULO:
        return False, "ID_HOJA_CALCULO no configurado."
    try:
        service = get_sheets_service()
        valores = [
            [
                terapeuta,
                tipo.lower(),
                nombre,
                fechas,
                horario,
                modalidad,
                precio,
                cupo,
                temario,
                activo,
            ]
        ]
        service.spreadsheets().values().append(
            spreadsheetId=config.ID_HOJA_CALCULO,
            range=f"{CATALOGO_TAB}!A:J",
            valueInputOption="USER_ENTERED",
            body={"values": valores},
        ).execute()
        invalidar_cache()
        return True, f"'{nombre}' agregado al catálogo."
    except Exception as e:
        logger.error("Error agregando al catálogo: %s", e)
        return False, str(e)


def actualizar_entrada_catalogo(
    terapeuta: str, nombre: str, campos: dict
) -> tuple[bool, str]:
    if not config.ID_HOJA_CALCULO:
        return False, "ID_HOJA_CALCULO no configurado."
    fila = _buscar_fila_catalogo(terapeuta, nombre)
    if fila is None:
        return False, f"No encontré '{nombre}' en tu catálogo."
    col_map = {
        "terapeuta": "A",
        "tipo": "B",
        "nombre": "C",
        "fechas": "D",
        "horario": "E",
        "modalidad": "F",
        "precio": "G",
        "cupo": "H",
        "temario": "I",
        "activo": "J",
    }
    try:
        service = get_sheets_service()
        for campo, valor in campos.items():
            if campo not in col_map:
                continue
            service.spreadsheets().values().update(
                spreadsheetId=config.ID_HOJA_CALCULO,
                range=f"{CATALOGO_TAB}!{col_map[campo]}{fila}",
                valueInputOption="USER_ENTERED",
                body={"values": [[valor]]},
            ).execute()
        invalidar_cache()
        return True, f"'{nombre}' actualizado."
    except Exception as e:
        logger.error("Error actualizando catálogo: %s", e)
        return False, str(e)


def desactivar_entrada_catalogo(terapeuta: str, nombre: str) -> tuple[bool, str]:
    return actualizar_entrada_catalogo(terapeuta, nombre, {"activo": "NO"})


def consultar_catalogo_drive(especialista: str = "todos"):
    """
    Consulta talleres y servicios publicados por terapeutas en Google Sheets.
    Los terapeutas editan la hoja 'Catalogo' del archivo en Drive.
    """
    filas = [_enriquecer_fila_catalogo(f) for f in _leer_filas_catalogo()]
    if not filas:
        return (
            "INSTRUCCIÓN PARA LA IA: No hay catálogo en Drive todavía o la hoja "
            "'Catalogo' está vacía. Usa consultar_precios_y_servicios como respaldo."
        )

    instruccion = (
        "INSTRUCCIÓN PARA LA IA: En talleres usa SIEMPRE aviso_estado y estado_taller "
        "(en_curso, por_iniciar, finalizado) sin que el paciente pregunte si ya empezó."
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
        return instruccion + " Catálogo de Drive: " + json.dumps(filtradas, ensure_ascii=False)

    return instruccion + " Catálogo completo de Drive: " + json.dumps(filas, ensure_ascii=False)


def obtener_cuentas_pago_texto() -> str:
    banorte = config.CUENTAS_OFICIALES["BANORTE"]
    banamex = config.CUENTAS_OFICIALES["BANAMEX"]
    return (
        f"BANORTE CLABE {banorte['clabe']} ({banorte['titular']}) | "
        f"BANAMEX CLABE {banamex['clabe']} ({banamex['titular']})"
    )
