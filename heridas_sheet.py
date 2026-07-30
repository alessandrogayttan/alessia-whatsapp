"""Hoja exclusiva Drive: inscritos e interesados del taller Sanando heridas."""
from __future__ import annotations

import logging
import re
from datetime import datetime

import pytz

import config
import storage
from google_client import get_drive_service, get_sheets_service

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)

TITULO_ARCHIVO = "Alessia — Taller Sanando heridas (inscritos e interesados)"
TAB_INSCRITOS = "Inscritos"
TAB_INTERESADOS = "Interesados"

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

_KV_ID = "id_hoja_heridas"
_KV_URL = "url_hoja_heridas"


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


def _emails_compartir() -> list[str]:
    raw = (config.HERIDAS_SHARE_EMAILS or "").strip()
    emails = [e.strip() for e in raw.split(",") if e.strip() and "@" in e]
    if not emails:
        emails = ["agenda.inpulso43@gmail.com"]
    # únicos preservando orden
    vistos: set[str] = set()
    out: list[str] = []
    for e in emails:
        k = e.lower()
        if k not in vistos:
            vistos.add(k)
            out.append(e)
    return out


def _id_configurado() -> str:
    return (config.ID_HOJA_HERIDAS or storage.obtener_app_config(_KV_ID) or "").strip()


def url_hoja_heridas() -> str:
    sid = _id_configurado()
    if not sid:
        return storage.obtener_app_config(_KV_URL) or ""
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit"


def _guardar_id(spreadsheet_id: str) -> None:
    storage.guardar_app_config(_KV_ID, spreadsheet_id)
    storage.guardar_app_config(
        _KV_URL, f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    )


def _formatear_cabeceras(service, spreadsheet_id: str) -> None:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    ids = {
        s["properties"]["title"]: s["properties"]["sheetId"]
        for s in meta.get("sheets", [])
    }
    reqs = []
    for titulo, headers in (
        (TAB_INSCRITOS, HEADERS_INSCRITOS),
        (TAB_INTERESADOS, HEADERS_INTERESADOS),
    ):
        sid = ids.get(titulo)
        if sid is None:
            continue
        reqs.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sid,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(headers),
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {
                                "red": 0.18,
                                "green": 0.31,
                                "blue": 0.51,
                            },
                            "textFormat": {
                                "bold": True,
                                "foregroundColor": {
                                    "red": 1,
                                    "green": 1,
                                    "blue": 1,
                                },
                            },
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }
        )
        reqs.append(
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount",
                }
            }
        )
    if reqs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": reqs}
        ).execute()


def _compartir(spreadsheet_id: str) -> None:
    drive = get_drive_service()
    for email in _emails_compartir():
        try:
            drive.permissions().create(
                fileId=spreadsheet_id,
                body={"type": "user", "role": "writer", "emailAddress": email},
                sendNotificationEmail=True,
                emailMessage=(
                    "Alessia creó este archivo exclusivo del taller "
                    "Sanando tus heridas del pasado (inscritos + interesados). "
                    "Ábrelo y usa 'Añadir acceso directo a Mi unidad' para tenerlo "
                    "al inicio de tu Drive."
                ),
            ).execute()
            logger.info("Hoja heridas compartida con %s", email)
        except Exception as e:
            logger.warning("No se pudo compartir hoja heridas con %s: %s", email, e)

    # Intentar dejarlo en la raíz de una carpeta compartida si está configurada
    parent = (config.HERIDAS_DRIVE_FOLDER_ID or "").strip()
    if parent:
        try:
            meta = drive.files().get(fileId=spreadsheet_id, fields="parents").execute()
            prev = meta.get("parents") or []
            drive.files().update(
                fileId=spreadsheet_id,
                addParents=parent,
                removeParents=",".join(prev) if prev else None,
                fields="id, parents",
            ).execute()
        except Exception as e:
            logger.warning("No se pudo mover hoja heridas a carpeta %s: %s", parent, e)


def _crear_spreadsheet() -> str:
    service = get_sheets_service()
    body = {
        "properties": {"title": TITULO_ARCHIVO},
        "sheets": [
            {"properties": {"title": TAB_INSCRITOS, "index": 0}},
            {"properties": {"title": TAB_INTERESADOS, "index": 1}},
        ],
    }
    creado = service.spreadsheets().create(body=body).execute()
    spreadsheet_id = creado["spreadsheetId"]
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{TAB_INSCRITOS}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [HEADERS_INSCRITOS]},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{TAB_INTERESADOS}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [HEADERS_INTERESADOS]},
    ).execute()
    _formatear_cabeceras(service, spreadsheet_id)
    _compartir(spreadsheet_id)
    _guardar_id(spreadsheet_id)
    logger.info("Creada hoja heridas: %s", spreadsheet_id)
    return spreadsheet_id


def asegurar_hoja_heridas(*, forzar_crear: bool = False) -> str:
    """Devuelve spreadsheetId; crea y comparte si no existe."""
    if not forzar_crear:
        existente = _id_configurado()
        if existente:
            return existente
    sid = _crear_spreadsheet()
    return sid


def _append_fila(tab: str, fila: list) -> bool:
    try:
        sid = asegurar_hoja_heridas()
        service = get_sheets_service()
        service.spreadsheets().values().append(
            spreadsheetId=sid,
            range=f"{tab}!A:Z",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [fila]},
        ).execute()
        return True
    except Exception as e:
        logger.error("Error escribiendo %s heridas: %s", tab, e)
        return False


def _norm_tel(telefono: str) -> str:
    return re.sub(r"\D", "", telefono or "")[-10:]


def _ya_inscrito_reciente(telefono: str) -> bool:
    """Evita filas duplicadas del mismo WhatsApp en Inscritos (últimas ~200)."""
    try:
        sid = _id_configurado()
        if not sid:
            return False
        service = get_sheets_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sid, range=f"{TAB_INSCRITOS}!C2:C200")
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
    """Índice 1-based de fila en Interesados si el teléfono ya existe."""
    try:
        sid = _id_configurado()
        if not sid:
            return None
        service = get_sheets_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sid, range=f"{TAB_INTERESADOS}!A2:F500")
            .execute()
        )
        target = _norm_tel(telefono)
        rows = result.get("values", [])
        for i, row in enumerate(rows):
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
        # Actualizar estatus si ya existe
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
        sid = asegurar_hoja_heridas()
        service = get_sheets_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sid, range=f"{TAB_INSCRITOS}!A2:I500")
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
                    spreadsheetId=sid,
                    range=f"{TAB_INSCRITOS}!F{fila}:G{fila}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[estatus, monto or (row[6] if len(row) > 6 else "")]]},
                ).execute()
                return True
        # No estaba: crear
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
            sid = asegurar_hoja_heridas()
            service = get_sheets_service()
            service.spreadsheets().values().update(
                spreadsheetId=sid,
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
        sid = _id_configurado()
        if not sid:
            return
        service = get_sheets_service()
        service.spreadsheets().values().update(
            spreadsheetId=sid,
            range=f"{TAB_INTERESADOS}!F{fila}",
            valueInputOption="USER_ENTERED",
            body={"values": [["Inscrito"]]},
        ).execute()
    except Exception as e:
        logger.debug("Marcar interesado inscrito: %s", e)
