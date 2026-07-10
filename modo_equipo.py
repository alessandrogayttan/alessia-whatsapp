"""Modo equipo Inpulso — Alessia como asistente IA completa para el staff interno."""
from __future__ import annotations

import logging
import threading

from google.genai import types

import config
from conversacion import (
    clave_conversacion_equipo,
    historial_para_gemini,
    registrar_turno_equipo,
    texto_desde_contenido,
)
from observability import registrar_fallo_gemini
from tools import obtener_contexto_fecha_actual

logger = logging.getLogger(__name__)

PROMPT_VERSION = "equipo-2026-07-09a"
_memoria_equipo: dict[str, object] = {}
_prompt_version_equipo: dict[str, str] = {}
_cerrojos_equipo: dict[str, threading.Lock] = {}

MENSAJE_RESCATE = (
    "Tuve un problema técnico procesando eso. ¿Me lo reenvías o lo partimos en pasos más pequeños?"
)

_GENAI = None


def _cliente():
    global _GENAI
    if _GENAI is None:
        from google import genai

        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY no configurada")
        _GENAI = genai.Client(api_key=config.GEMINI_API_KEY)
    return _GENAI


def _instrucciones_equipo(nombre: str) -> str:
    return f"""
Eres *Alessia*, asistente de inteligencia artificial del equipo interno de Inpulso 43.
Estás hablando con *{nombre}* (uso interno — NO es un paciente).

NATURALEZA DE ESTE MODO:
- Tienes las capacidades completas de un asistente IA avanzado (Gemini): razonamiento, redacción,
  análisis, síntesis, lluvia de ideas, código, tablas, planes de trabajo, emails, guiones, etc.
- Puedes reconocer que eres una IA si te preguntan; con pacientes nunca lo harías, pero aquí es equipo.
- Responde en el idioma del usuario (por defecto español de México).
- Tono: colega profesional, claro y útil; sin sermones ni limitaciones artificiales de "solo recepción".

ARCHIVOS Y DOCUMENTOS (CRÍTICO):
- Si envían imagen, PDF, audio, video o documento: léelo/analízalo por completo.
- Extrae información, resume, reestructura, corrige, da formato, propone esquemas o entregables listos.
- Si piden "dame esto en bullets / tabla / correo / guion", hazlo directamente.
- Si el archivo es ilegible, dilo y pide otro formato o más contexto.

TRABAJO CON INPULSO:
- Conoces que Inpulso 43 es clínica de psicología, nutrición, medicina y talleres en Zapopan.
- Sitio: {config.CLINICA_WEB_URL}
- Puedes ayudar con copy, protocolos internos, ideas de talleres, organización — sin inventar datos
  clínicos oficiales que no te hayan dado.
- Datos de pacientes: trata como confidenciales; no los reutilices fuera del contexto del pedido.

LÍMITES SANOS:
- No sustituyes criterio clínico ni legal; sugiere revisión humana cuando aplique.
- Si piden algo enorme, entrégalo por partes claras.

Eres la herramienta de productividad del equipo. Sé excelente.
"""


def _obtener_chat_equipo(telefono: str, nombre: str):
    clave_mem = f"{telefono}:{PROMPT_VERSION}"
    conv = clave_conversacion_equipo(telefono)
    if clave_mem not in _memoria_equipo or _prompt_version_equipo.get(telefono) != PROMPT_VERSION:
        _memoria_equipo[clave_mem] = _cliente().chats.create(
            model=config.EQUIPO_GEMINI_MODEL,
            history=historial_para_gemini(conv),
            config=types.GenerateContentConfig(
                system_instruction=_instrucciones_equipo(nombre),
                temperature=config.EQUIPO_GEMINI_TEMPERATURE,
            ),
        )
        _prompt_version_equipo[telefono] = PROMPT_VERSION
    return _memoria_equipo[clave_mem]


def envolver_mensaje_equipo(telefono: str, contenido):
    """Contexto mínimo para el equipo — sin reglas de paciente."""
    nombre = config.identificar_miembro_equipo(telefono) or "Equipo"
    ctx = (
        obtener_contexto_fecha_actual()
        + f"[Sistema: MODO EQUIPO INTERNO — {nombre}. Asistente IA completa.]\n"
    )
    if isinstance(contenido, str):
        return ctx + contenido
    if isinstance(contenido, list):
        return [types.Part(text=ctx)] + contenido
    return contenido


def es_modo_equipo(telefono: str) -> bool:
    return bool(config.ENABLE_MODO_EQUIPO and config.identificar_miembro_equipo(telefono))


def procesar_mensaje_equipo(telefono: str, contenido):
    """Procesa mensaje de un miembro del equipo y devuelve texto de respuesta."""
    nombre = config.identificar_miembro_equipo(telefono)
    if not nombre:
        return None

    if telefono not in _cerrojos_equipo:
        _cerrojos_equipo[telefono] = threading.Lock()

    with _cerrojos_equipo[telefono]:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
        import time

        chat = _obtener_chat_equipo(telefono, nombre)
        timeout = config.EQUIPO_GEMINI_TIMEOUT

        for intento in range(2):
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(chat.send_message, contenido)
                    respuesta = future.result(timeout=timeout)
                texto = (getattr(respuesta, "text", None) or "").strip()
                if texto:
                    entrada = texto_desde_contenido(contenido)
                    if not entrada:
                        entrada = "[archivo multimedia del equipo]"
                    registrar_turno_equipo(telefono, entrada, texto)
                    return texto
            except FuturesTimeout:
                logger.error("Timeout Gemini equipo %s intento %s", telefono, intento + 1)
                registrar_fallo_gemini(f"equipo:{telefono}")
                if intento == 0:
                    time.sleep(2)
                    continue
            except Exception as e:
                logger.exception("Error Gemini equipo %s: %s", telefono, e)
                registrar_fallo_gemini(f"equipo:{telefono}")
                if intento == 0:
                    time.sleep(2)
                    continue
                break

    return MENSAJE_RESCATE


def invalidar_chat_equipo(telefono: str):
    for k in list(_memoria_equipo.keys()):
        if k.startswith(f"{telefono}:"):
            _memoria_equipo.pop(k, None)
    _prompt_version_equipo.pop(telefono, None)
