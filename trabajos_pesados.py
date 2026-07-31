"""Cola durable de trabajos pesados (sync Sheets, etc.).

WhatsApp solo encola + acusa; el scheduler ejecuta y confirma.
Así un OOM/reinicio no deja el sync “en el aire” sin respuesta.
"""
from __future__ import annotations

import logging

import config
import storage

logger = logging.getLogger(__name__)

TIPO_SYNC_HERIDAS = "sync_heridas"
TIPO_SYNC_ANALYTICS = "sync_analytics"


def encolar_sync_heridas(telefono: str) -> int:
    storage.renovar_sesion_equipo(telefono, config.EQUIPO_SESION_HORAS)
    return storage.encolar_trabajo_pesado(TIPO_SYNC_HERIDAS, telefono)


def encolar_sync_analytics(telefono: str) -> int:
    storage.renovar_sesion_equipo(telefono, config.EQUIPO_SESION_HORAS)
    return storage.encolar_trabajo_pesado(TIPO_SYNC_ANALYTICS, telefono)


def responder_estado_trabajo(telefono: str) -> str | None:
    """Respuesta a «ya quedó?» según el último trabajo de ese WhatsApp."""
    job = storage.ultimo_trabajo_telefono(telefono)
    if not job:
        return None
    tipo = job.get("tipo") or ""
    etiqueta = {
        TIPO_SYNC_HERIDAS: "hoja de heridas",
        TIPO_SYNC_ANALYTICS: "hoja de Analytics",
    }.get(tipo, tipo)
    estado = job.get("estado") or ""
    if estado in ("pendiente", "procesando"):
        return (
            f"Sigue en proceso la *{etiqueta}*… te confirmo aquí en cuanto termine. "
            "Si pasan más de 2 minutos, reintenta el comando de sync."
        )
    if estado == "ok":
        detalle = (job.get("resultado") or "").strip()
        when = (job.get("actualizado_at") or "")[:19]
        if detalle:
            return f"Sí — *{etiqueta}* quedó lista ({when}).\n\n{detalle}"
        return f"Sí — *{etiqueta}* quedó lista ({when})."
    if estado == "error":
        err = (job.get("error") or "error desconocido").strip()
        return f"El sync de *{etiqueta}* falló: {err}\nReintenta el comando en Modo Pro."
    return None


def procesar_un_trabajo() -> bool:
    """Ejecuta como máximo un trabajo. Devuelve True si procesó algo."""
    storage.reencolar_trabajos_procesando_atascados(8)
    job = storage.reclamar_trabajo_pesado()
    if not job:
        return False

    trabajo_id = int(job["id"])
    tipo = job["tipo"]
    telefono = job["telefono"]
    logger.info("Trabajo pesado #%s tipo=%s …%s", trabajo_id, tipo, telefono[-4:])

    try:
        if tipo == TIPO_SYNC_HERIDAS:
            from heridas_sheet import sincronizar_panel_heridas

            resultado = sincronizar_panel_heridas()
            quien = (
                config.identificar_personal_inpulso(telefono)
                or storage.obtener_nombre_equipo_sesion(telefono)
                or "Equipo"
            )
            msg = f"Listo, *{quien}* ✨\n\n{resultado}"
        elif tipo == TIPO_SYNC_ANALYTICS:
            from analytics import sincronizar_panel_analytics

            resultado = sincronizar_panel_analytics()
            quien = (
                config.identificar_personal_inpulso(telefono)
                or storage.obtener_nombre_equipo_sesion(telefono)
                or "Equipo"
            )
            msg = f"Listo, *{quien}* ✨\n\n{resultado}"
        else:
            raise RuntimeError(f"Tipo de trabajo desconocido: {tipo}")

        storage.finalizar_trabajo_pesado(trabajo_id, ok=True, resultado=msg)
        storage.renovar_sesion_equipo(telefono, config.EQUIPO_SESION_HORAS)
        _avisar_whatsapp(telefono, msg)
        return True
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        logger.exception("Trabajo pesado #%s falló: %s", trabajo_id, err)
        storage.finalizar_trabajo_pesado(trabajo_id, ok=False, error=err)
        _avisar_whatsapp(
            telefono,
            f"No pude completar el trabajo ({err}). WhatsApp sigue activo; reintenta en un minuto.",
        )
        return True


def _avisar_whatsapp(telefono: str, texto: str) -> None:
    try:
        from whatsapp import enviar_mensaje_whatsapp

        enviar_mensaje_whatsapp(telefono, texto)
    except Exception as e:
        logger.error("No pude avisar WhatsApp tras trabajo: %s", e)
