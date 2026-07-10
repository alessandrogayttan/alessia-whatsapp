"""Historial persistente y claves unificadas web + WhatsApp."""
from __future__ import annotations

import logging

from google.genai import types

import config
import storage

logger = logging.getLogger(__name__)


def clave_web(session_id: str) -> str:
    return f"web:{session_id}"


def clave_conversacion_whatsapp(telefono: str) -> str:
    return telefono


def clave_conversacion_web(session_id: str, telefono_vinculado: str | None = None) -> str:
    if telefono_vinculado:
        return telefono_vinculado
    return clave_web(session_id)


def vincular_conversacion_web(session_id: str, telefono: str) -> int:
    """Une historial web con el del WhatsApp del paciente."""
    origen = clave_web(session_id)
    destino = telefono
    movidos = storage.migrar_conversacion_clave(origen, destino)
    if movidos:
        logger.info("Conversación web %s fusionada con %s (%s msgs)", session_id, telefono, movidos)
    return movidos


def texto_desde_contenido(contenido) -> str:
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        partes = []
        for parte in contenido:
            texto = getattr(parte, "text", None)
            if texto:
                partes.append(str(texto))
            elif getattr(parte, "inline_data", None):
                partes.append("[archivo multimedia enviado]")
        return " ".join(partes).strip()
    return ""


def historial_para_gemini(clave: str, limite: int | None = None) -> list:
    if not config.ENABLE_CONVERSACION_PERSISTENTE:
        return []
    limite = limite or config.CONVERSACION_MAX_TURNOS
    mensajes = storage.obtener_mensajes_conversacion(clave, limite=limite * 2)
    historial = []
    for msg in mensajes:
        rol = "model" if msg["rol"] == "model" else "user"
        historial.append(
            types.Content(
                role=rol,
                parts=[types.Part(text=msg["contenido"][:4000])],
            )
        )
    return historial


def registrar_turno(
    clave: str,
    canal: str,
    mensaje_usuario: str,
    respuesta_modelo: str,
) -> None:
    if not config.ENABLE_CONVERSACION_PERSISTENTE:
        return
    usuario = (mensaje_usuario or "").strip()
    modelo = (respuesta_modelo or "").strip()
    if usuario:
        storage.guardar_mensaje_conversacion(clave, canal, "user", usuario)
    if modelo:
        storage.guardar_mensaje_conversacion(clave, canal, "model", modelo)


def registrar_turno_whatsapp(telefono: str, contenido_entrada, respuesta: str) -> None:
    usuario = texto_desde_contenido(contenido_entrada)
    registrar_turno(clave_conversacion_whatsapp(telefono), "whatsapp", usuario, respuesta)


def registrar_turno_web(
    session_id: str,
    telefono: str | None,
    mensaje_usuario: str,
    respuesta: str,
) -> None:
    clave = clave_conversacion_web(session_id, telefono)
    registrar_turno(clave, "web", mensaje_usuario, respuesta)
