"""Cola persistente de mensajes WhatsApp — sobrevive reinicios del proceso."""
import logging

import storage

logger = logging.getLogger(__name__)


def encolar_mensaje_texto(telefono: str, contenido: str) -> int:
    """Encola un mensaje de texto para procesamiento por IA."""
    return storage.encolar_mensaje_ia(telefono, contenido)


def procesar_cola(max_items: int = 10) -> int:
    """Procesa hasta max_items mensajes pendientes. Devuelve cantidad procesada."""
    from chat import procesar_mensaje_ia

    procesados = 0
    for item in storage.obtener_mensajes_pendientes(max_items):
        msg_id = item["id"]
        telefono = item["telefono"]
        contenido = item["contenido"]
        intentos = item["intentos"]
        if not storage.marcar_mensaje_procesando(msg_id):
            continue
        try:
            procesar_mensaje_ia(telefono, contenido)
            storage.marcar_mensaje_completado(msg_id)
            procesados += 1
        except Exception as e:
            logger.exception("Error procesando cola id=%s tel=%s: %s", msg_id, telefono, e)
            storage.marcar_mensaje_fallido(msg_id, intentos + 1, str(e)[:500])
    return procesados


def reintentar_fallidos(max_items: int = 5) -> int:
    return storage.reencolar_mensajes_fallidos(max_items)


def limpiar_antiguos(dias: int = 7) -> int:
    from datetime import datetime, timedelta

    cutoff = (datetime.utcnow() - timedelta(days=dias)).isoformat()
    return storage.limpiar_cola_antigua(cutoff)
