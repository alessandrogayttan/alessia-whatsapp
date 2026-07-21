"""Conocimiento clínico para pacientes + FAQ de consultas frecuentes."""
from __future__ import annotations

import logging
import re
from datetime import datetime

import pytz

import config
import storage

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)

HOJA_CONOCIMIENTO = "Conocimiento"
HOJA_FAQ = "FAQ_Pacientes"

_HEADERS_CONOCIMIENTO = [
    "ID",
    "Tema",
    "Contenido",
    "Palabras_clave",
    "Quien",
    "Actualizado",
    "Activo",
]
_HEADERS_FAQ = [
    "Pregunta",
    "Veces",
    "Ultima_vez",
    "Respuesta_oficial",
    "Estado",
    "Notas",
]


def _ahora() -> str:
    return datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")


def _normalizar_pregunta(texto: str) -> str:
    t = (texto or "").strip().lower()
    t = re.sub(r"[¿?¡!.,;:]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:200]


def parece_consulta_informativa(texto: str) -> bool:
    """Heurística simple: ¿parece pregunta de info (precios, fechas, etc.)?"""
    t = (texto or "").strip().lower()
    if len(t) < 8 or len(t) > 280:
        return False
    if any(x in t for x in ("modo equipo", "salir equipo", "eliminar datos")):
        return False
    if "¿" in texto or "?" in texto:
        return True
    inicios = (
        "cuanto",
        "cuánto",
        "cuando",
        "cuándo",
        "donde",
        "dónde",
        "como",
        "cómo",
        "que costo",
        "qué costo",
        "precio",
        "cuesta",
        "horario",
        "abre",
        "taller",
        "hay cupo",
        "inscripcion",
        "inscripción",
    )
    return any(t.startswith(i) or f" {i}" in f" {t}" for i in inicios)


def guardar_conocimiento(
    tema: str,
    contenido: str,
    *,
    palabras_clave: str = "",
    quien: str = "equipo",
    sync_sheets: bool = True,
) -> str:
    """Guarda o actualiza un bloque de conocimiento para pacientes."""
    tema_n = (tema or "").strip()[:120]
    cont = (contenido or "").strip()
    if not tema_n or not cont:
        return "Falta tema o contenido. Ejemplo: tema='taller heridas', contenido='Cuesta $2500...'."
    kid = storage.upsert_conocimiento_clinica(
        tema=tema_n,
        contenido=cont,
        palabras_clave=(palabras_clave or "").strip()[:300],
        quien=(quien or "equipo").strip()[:80],
    )
    if sync_sheets:
        try:
            _sincronizar_conocimiento_a_sheets()
        except Exception as e:
            logger.warning("Sync Conocimiento a Sheets: %s", e)
    return (
        f"ÉXITO: Guardé el conocimiento #{kid} (*{tema_n}*) para pacientes. "
        "Cuando pregunten por eso, Alessia lo usará."
    )


def listar_conocimiento(limite: int = 30) -> str:
    filas = storage.listar_conocimiento_clinica(activos_solo=True, limite=limite)
    if not filas:
        return "Aún no hay conocimiento guardado para pacientes."
    lineas = ["*Conocimiento activo para pacientes:*"]
    for f in filas:
        preview = (f["contenido"] or "")[:120].replace("\n", " ")
        lineas.append(f"• #{f['id']} *{f['tema']}* — {preview}…")
    return "\n".join(lineas)


def borrar_conocimiento(conocimiento_id: int) -> str:
    ok = storage.desactivar_conocimiento_clinica(int(conocimiento_id))
    if not ok:
        return f"No encontré el conocimiento #{conocimiento_id}."
    try:
        _sincronizar_conocimiento_a_sheets()
    except Exception as e:
        logger.warning("Sync tras borrar conocimiento: %s", e)
    return f"ÉXITO: Desactivé el conocimiento #{conocimiento_id}."


def buscar_conocimiento_clinica(consulta: str) -> str:
    """Tool paciente: busca en lo que el equipo enseñó (precios, fechas, etc.)."""
    hits = storage.buscar_conocimiento_clinica(consulta or "", limite=5)
    if not hits:
        return (
            "INSTRUCCIÓN: No hay conocimiento interno guardado que coincida. "
            "Usa consultar_precios_y_servicios, consultar_talleres_y_servicios o "
            "consultar_sitio_inpulso. Si no hay dato seguro, dilo y ofrece recepción."
        )
    bloques = []
    for h in hits:
        bloques.append(
            f"[Conocimiento equipo — {h['tema']}]\n{h['contenido']}"
        )
    return (
        "Usa esta información oficial del equipo (prioridad sobre inventar):\n\n"
        + "\n\n---\n\n".join(bloques)
    )


def registrar_consulta_paciente(texto: str, telefono: str = "") -> None:
    if not parece_consulta_informativa(texto):
        return
    norm = _normalizar_pregunta(texto)
    if len(norm) < 6:
        return
    try:
        storage.registrar_pregunta_frecuente(norm, telefono=telefono)
    except Exception as e:
        logger.debug("No se registró FAQ: %s", e)


def _asegurar_hojas(service) -> None:
    from tools import _asegurar_hoja

    _asegurar_hoja(service, HOJA_CONOCIMIENTO, _HEADERS_CONOCIMIENTO)
    _asegurar_hoja(service, HOJA_FAQ, _HEADERS_FAQ)


def _sincronizar_conocimiento_a_sheets() -> None:
    if not config.ID_HOJA_CALCULO:
        return
    from google_client import get_sheets_service

    service = get_sheets_service()
    _asegurar_hojas(service)
    filas = storage.listar_conocimiento_clinica(activos_solo=False, limite=500)
    values = [_HEADERS_CONOCIMIENTO]
    for f in filas:
        values.append(
            [
                f["id"],
                f["tema"],
                f["contenido"],
                f.get("palabras_clave") or "",
                f.get("quien") or "",
                f.get("actualizado_at") or "",
                "SI" if f.get("activo") else "NO",
            ]
        )
    service.spreadsheets().values().clear(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{HOJA_CONOCIMIENTO}!A:G",
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{HOJA_CONOCIMIENTO}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()


def sincronizar_faq_a_sheets(top: int = 80) -> int:
    """Escribe ranking de preguntas frecuentes. Preserva Respuesta_oficial si ya existía."""
    if not config.ID_HOJA_CALCULO:
        return 0
    from google_client import get_sheets_service

    service = get_sheets_service()
    _asegurar_hojas(service)

    # Respuestas ya escritas por el desarrollador
    existentes: dict[str, tuple[str, str, str]] = {}
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=config.ID_HOJA_CALCULO, range=f"{HOJA_FAQ}!A:F")
            .execute()
        )
        for row in result.get("values", [])[1:]:
            if not row:
                continue
            preg = (row[0] or "").strip().lower()
            if not preg:
                continue
            resp = row[3] if len(row) > 3 else ""
            estado = row[4] if len(row) > 4 else ""
            notas = row[5] if len(row) > 5 else ""
            existentes[preg] = (resp or "", estado or "", notas or "")
    except Exception as e:
        logger.debug("Lectura FAQ previa: %s", e)

    ranking = storage.top_preguntas_frecuentes(limite=top)
    values = [_HEADERS_FAQ]
    for item in ranking:
        preg = item["pregunta"]
        prev = existentes.get(preg.lower(), ("", "PENDIENTE", ""))
        resp, estado, notas = prev
        if resp.strip() and estado.upper() != "RESPONDIDA":
            estado = "RESPONDIDA"
        if not estado:
            estado = "PENDIENTE"
        values.append(
            [
                preg,
                item["veces"],
                item.get("ultima_vez") or "",
                resp,
                estado,
                notas,
            ]
        )

    service.spreadsheets().values().clear(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{HOJA_FAQ}!A:F",
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{HOJA_FAQ}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()

    # Importar solo respuestas oficiales ya escritas
    importados = 0
    for row in values[1:]:
        preg = row[0] if len(row) > 0 else ""
        resp = row[3] if len(row) > 3 else ""
        estado = (row[4] if len(row) > 4 else "") or ""
        if not (resp or "").strip():
            continue
        if str(estado).upper() not in ("RESPONDIDA", "PENDIENTE", ""):
            continue
        # Solo materializa si hay respuesta; upsert por tema FAQ
        tema = f"FAQ: {(preg or '')[:80]}"
        guardar_conocimiento(
            tema,
            resp.strip(),
            palabras_clave=preg,
            quien="FAQ_Sheets",
            sync_sheets=False,
        )
        importados += 1
    if importados:
        try:
            _sincronizar_conocimiento_a_sheets()
        except Exception as e:
            logger.warning("Re-sync conocimiento tras FAQ: %s", e)
    return len(values) - 1


def inicializar_hojas_conocimiento() -> str:
    if not config.ID_HOJA_CALCULO:
        return "Falta ID_HOJA_CALCULO"
    from google_client import get_sheets_service

    service = get_sheets_service()
    _asegurar_hojas(service)
    _sincronizar_conocimiento_a_sheets()
    sincronizar_faq_a_sheets()
    return (
        f"Listo. Hojas '{HOJA_CONOCIMIENTO}' y '{HOJA_FAQ}' en "
        f"https://docs.google.com/spreadsheets/d/{config.ID_HOJA_CALCULO}"
    )


# --- Wrappers para Gemini tools (nombres claros) ---


def guardar_conocimiento_pacientes(
    tema: str,
    contenido: str,
    palabras_clave: str = "",
) -> str:
    """
    Modo equipo: guarda información oficial para que Alessia se la diga a pacientes
    (precios, fechas de talleres, horarios, políticas, etc.).
    """
    quien = "equipo"
    try:
        # Si hay contexto de teléfono de equipo en storage sesión — opcional
        pass
    except Exception:
        pass
    return guardar_conocimiento(
        tema, contenido, palabras_clave=palabras_clave, quien=quien, sync_sheets=True
    )


def listar_conocimiento_pacientes() -> str:
    """Modo equipo: lista el conocimiento activo para pacientes."""
    return listar_conocimiento()


def borrar_conocimiento_pacientes(conocimiento_id: int) -> str:
    """Modo equipo: desactiva un conocimiento por ID (ver listar_conocimiento_pacientes)."""
    return borrar_conocimiento(conocimiento_id)
