"""Cola persistente de mensajes WhatsApp — sobrevive reinicios del proceso."""
import logging

import storage
from cola_contenido import deserializar_contenido, media_id_de_payload, serializar_contenido

logger = logging.getLogger(__name__)

COLA_STUCK_MINUTOS = 10


def encolar_mensaje_texto(telefono: str, contenido: str) -> int:
    """Encola un mensaje de texto para procesamiento por IA."""
    return storage.encolar_mensaje_ia(telefono, contenido)


def encolar_contenido_ia(telefono: str, contenido) -> int:
    """Encola texto o multimodal (Parts) de forma durable."""
    payload, _media_id = serializar_contenido(contenido)
    return storage.encolar_mensaje_ia(telefono, payload)


def recuperar_atascados(minutos: int | None = None) -> int:
    """Reencola mensajes 'procesando' viejos (p. ej. tras crash)."""
    n = storage.reencolar_mensajes_procesando_atascados(
        minutos if minutos is not None else COLA_STUCK_MINUTOS
    )
    if n:
        logger.warning("Cola: recuperados %s mensajes atascados en procesando", n)
    return n


def procesar_cola(max_items: int = 10) -> int:
    """Procesa hasta max_items mensajes pendientes. Devuelve cantidad procesada."""
    from chat import procesar_mensaje_ia

    recuperar_atascados()
    procesados = 0
    for item in storage.obtener_mensajes_pendientes(max_items):
        msg_id = item["id"]
        telefono = item["telefono"]
        payload = item["contenido"]
        intentos = item["intentos"]
        if not storage.marcar_mensaje_procesando(msg_id):
            continue
        media_id = media_id_de_payload(payload)
        try:
            contenido = deserializar_contenido(payload)
            procesar_mensaje_ia(telefono, contenido)
            storage.marcar_mensaje_completado(msg_id)
            if media_id:
                storage.borrar_cola_media(media_id)
            procesados += 1
        except Exception as e:
            logger.exception("Error procesando cola id=%s tel=%s: %s", msg_id, telefono, e)
            storage.marcar_mensaje_fallido(msg_id, intentos + 1, str(e)[:500])
    return procesados


def reintentar_fallidos(max_items: int = 5) -> int:
    return storage.reencolar_mensajes_fallidos(max_items)


def limpiar_antiguos(dias: int = 7) -> int:
    from datetime import timedelta

    cutoff = (storage._utcnow() - timedelta(days=dias)).isoformat()
    return storage.limpiar_cola_antigua(cutoff)
