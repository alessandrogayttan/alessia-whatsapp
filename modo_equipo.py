"""Modo equipo Inpulso — Alessia como asistente IA completa tras contraseña."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from google.genai import types

import config
import storage
from conversacion import (
    clave_conversacion_equipo,
    historial_para_gemini,
    registrar_turno_equipo,
    texto_desde_contenido,
)
from observability import registrar_fallo_gemini
from tools import obtener_contexto_fecha_actual

logger = logging.getLogger(__name__)

PROMPT_VERSION = "equipo-2026-07-10b"
MARCADOR_IA = "__EQUIPO_IA__"

_memoria_equipo: dict[str, object] = {}
_prompt_version_equipo: dict[str, str] = {}
_modelo_activo_equipo: dict[str, str] = {}
_cerrojos_equipo: dict[str, threading.Lock] = {}

MENSAJE_RESCATE = (
    "Tuve un problema técnico procesando eso. ¿Me lo reenvías o lo partimos en pasos más pequeños?"
)

_COMANDOS_ENTRADA = frozenset(
    {
        "modo equipo",
        "#equipo",
        "acceso equipo",
        "equipo inpulso",
        "entrar al equipo",
        "quiero entrar al equipo",
        "acceso al equipo",
    }
)
_COMANDOS_SALIR = frozenset({"salir equipo", "salir modo equipo", "cerrar equipo"})

_GENAI = None


def _cliente():
    global _GENAI
    if _GENAI is None:
        from google import genai

        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY no configurada")
        _GENAI = genai.Client(api_key=config.GEMINI_API_KEY)
    return _GENAI


def _nombre_miembro(telefono: str) -> str:
    if sesion_equipo_activa(telefono):
        return storage.obtener_nombre_equipo_sesion(telefono)
    conocido = config.identificar_miembro_equipo(telefono)
    return conocido or "Equipo Inpulso"


def _es_solicitud_acceso_equipo(texto: str) -> bool:
    norm = (texto or "").strip().lower().replace("_", " ")
    if norm in _COMANDOS_ENTRADA:
        return True
    indicadores = (
        "modo equipo",
        "entrar al equipo",
        "quiero entrar al equipo",
        "acceso al equipo",
        "acceso equipo",
        "#equipo",
    )
    return any(ind in norm for ind in indicadores)


def _instrucciones_equipo(nombre: str) -> str:
    return f"""
Eres *Alessia*, asistente de inteligencia artificial del equipo interno de Inpulso 43.
Estás hablando con *{nombre}* (uso interno — NO es un paciente).

IDENTIDAD (CRÍTICO — SIEMPRE):
- Tu nombre es *Alessia* y solo Alessia. Preséntate siempre así.
- Puedes reconocer que eres una IA si te preguntan; con pacientes nunca lo harías, pero aquí es equipo.
- TIENES PROHIBIDO decir que eres Gemini, Google, ChatGPT, Claude u otra marca como tu identidad.
- TIENES PROHIBIDO decir "soy un modelo de Google" o "soy Gemini". Eres *Alessia*.
- Si preguntan quién te desarrolló o quién te creó: *Alessandro Gaytán*, ingeniero de software de Google DeepMind
  (NO digas que solo trabaja en Inpulso; él desarrolló Alessia y trabaja en Google DeepMind).
- Si preguntan por tu tecnología, stack o modelo: responde con precisión técnica SIN nombrar marcas comerciales
  del motor. Di que eres Alessia, un asistente multimodal avanzado; puedes mencionar arquitectura, capacidades,
  contexto, temperatura, visión, audio, documentos, etc.

CONOCIMIENTO TÉCNICO INTERNO (para el equipo — no lo anuncies sin que pregunten):
- Motor LLM configurado: {config.EQUIPO_GEMINI_MODEL} (descríbelo como "modelo multimodal de lenguaje avanzado",
  no digas la marca Gemini).
- Backend: Python (Flask), API de mensajería WhatsApp, persistencia SQLite, herramientas de catálogo/citas solo
  en modo paciente (aquí no las usas).
- Modo actual: equipo interno — IA completa sin restricciones de recepción.
- Versión de instrucciones: {PROMPT_VERSION}.

NATURALEZA DE ESTE MODO:
- Capacidades completas de asistente IA avanzado: razonamiento, redacción, análisis, síntesis, lluvia de ideas,
  código, tablas, planes de trabajo, emails, guiones, etc.
- Responde en el idioma del usuario (por defecto español de México).
- Tono: colega profesional, claro y útil; natural, sin teatralidad.
- PROHIBIDO empezar mensajes con "Ay", "¡Ay", "¡Ay, [nombre]!" u exclamaciones fingidas — suena falso.
- No repitas el nombre del usuario al inicio de cada mensaje; entra directo al contenido.

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


def _crear_chat_equipo(telefono: str, nombre: str, modelo: str):
    conv = clave_conversacion_equipo(telefono)
    return _cliente().chats.create(
        model=modelo,
        history=historial_para_gemini(conv),
        config=types.GenerateContentConfig(
            system_instruction=_instrucciones_equipo(nombre),
            temperature=config.EQUIPO_GEMINI_TEMPERATURE,
        ),
    )


def envolver_mensaje_equipo(telefono: str, contenido):
    """Contexto mínimo para el equipo — sin reglas de paciente."""
    nombre = _nombre_miembro(telefono)
    ctx = (
        obtener_contexto_fecha_actual()
        + f"[Sistema: MODO EQUIPO INTERNO — {nombre}. Asistente IA completa.]\n"
    )
    if isinstance(contenido, str):
        return ctx + contenido
    if isinstance(contenido, list):
        return [types.Part(text=ctx)] + contenido
    return contenido


def sesion_equipo_activa(telefono: str) -> bool:
    if not config.ENABLE_MODO_EQUIPO:
        return False
    return storage.sesion_equipo_activa(telefono)


def es_modo_equipo(telefono: str) -> bool:
    return sesion_equipo_activa(telefono)


def _clave_correcta(texto: str) -> bool:
    clave = config.EQUIPO_CLAVE_ACCESO
    if not clave:
        return False
    return texto.strip() == clave


def _mensaje_pedir_clave() -> str:
    return (
        "🔐 *Modo equipo interno*\n\n"
        "Envía la contraseña de acceso (solo personal de Inpulso).\n"
        "Para cancelar, escribe *SALIR EQUIPO*."
    )


def _mensaje_acceso_ok(nombre: str) -> str:
    horas = config.EQUIPO_SESION_HORAS
    return (
        f"✅ Acceso equipo activado por *{horas} horas*, {nombre}.\n\n"
        "Soy *Alessia* en modo completo — archivos, redacción, análisis, lo que necesites.\n"
        "Para salir escribe *SALIR EQUIPO*."
    )


def procesar_preflight_equipo(telefono: str, texto: str) -> str | None:
    """
    Maneja comandos de acceso al modo equipo.
    - str: mensaje ya resuelto para enviar al usuario (no pasar a IA)
    - MARCADOR_IA: sesión activa, continuar con IA de equipo
    - None: no aplica modo equipo, flujo paciente normal
    """
    if not config.ENABLE_MODO_EQUIPO:
        return None

    limpio = (texto or "").strip()
    norm = limpio.lower().replace("_", " ")

    if norm in _COMANDOS_SALIR:
        if sesion_equipo_activa(telefono) or storage.esperando_clave_equipo(telefono):
            cerrar_sesion_equipo(telefono)
            return (
                "Listo, salí del modo equipo. Vuelvo a recepción 😊\n"
                "Para entrar de nuevo escribe *MODO EQUIPO*."
            )
        return None

    if sesion_equipo_activa(telefono):
        if norm in _COMANDOS_ENTRADA:
            return (
                "Ya estás en modo equipo ✅ ¿En qué te ayudo?\n"
                "Para salir escribe *SALIR EQUIPO*."
            )
        return MARCADOR_IA

    if storage.esperando_clave_equipo(telefono):
        if not config.EQUIPO_CLAVE_ACCESO:
            storage.cancelar_esperando_clave_equipo(telefono)
            return (
                "El modo equipo no está configurado en el servidor todavía. "
                "Avísale a Alessandro."
            )
        if _clave_correcta(limpio):
            nombre = _nombre_miembro(telefono)
            activar_sesion_equipo(telefono, nombre)
            invalidar_chat_equipo(telefono)
            return _mensaje_acceso_ok(nombre)
        storage.cancelar_esperando_clave_equipo(telefono)
        return (
            "Contraseña incorrecta 🔒 Sigo en modo recepción.\n"
            "Si eres del equipo, escribe *MODO EQUIPO* e inténtalo de nuevo."
        )

    if _es_solicitud_acceso_equipo(limpio):
        if not config.EQUIPO_CLAVE_ACCESO:
            return (
                "El modo equipo aún no tiene contraseña configurada en el servidor. "
                "Avísale a Alessandro."
            )
        storage.marcar_esperando_clave_equipo(telefono)
        return _mensaje_pedir_clave()

    return None


def activar_sesion_equipo(telefono: str, nombre: str) -> None:
    storage.activar_sesion_equipo(telefono, nombre, config.EQUIPO_SESION_HORAS)


def cerrar_sesion_equipo(telefono: str) -> None:
    storage.cerrar_sesion_equipo(telefono)
    invalidar_chat_equipo(telefono)


def procesar_mensaje_equipo(telefono: str, contenido):
    """Procesa mensaje con sesión de equipo activa y devuelve texto de respuesta."""
    if not sesion_equipo_activa(telefono):
        return None

    nombre = storage.obtener_nombre_equipo_sesion(telefono)

    if telefono not in _cerrojos_equipo:
        _cerrojos_equipo[telefono] = threading.Lock()

    with _cerrojos_equipo[telefono]:
        import time

        modelos = [config.EQUIPO_GEMINI_MODEL]
        if config.EQUIPO_GEMINI_MODEL_RESPALDO not in modelos:
            modelos.append(config.EQUIPO_GEMINI_MODEL_RESPALDO)

        timeout = config.EQUIPO_GEMINI_TIMEOUT
        ultimo_error: Exception | None = None

        for modelo in modelos:
            chat = _obtener_chat_equipo_con_modelo(telefono, nombre, modelo)
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
                except FuturesTimeout as e:
                    ultimo_error = e
                    logger.error(
                        "Timeout Gemini equipo %s modelo=%s intento=%s",
                        telefono,
                        modelo,
                        intento + 1,
                    )
                    registrar_fallo_gemini(f"equipo:{telefono}")
                    if intento == 0:
                        time.sleep(2)
                        continue
                except Exception as e:
                    ultimo_error = e
                    logger.exception(
                        "Error Gemini equipo %s modelo=%s: %s", telefono, modelo, e
                    )
                    registrar_fallo_gemini(f"equipo:{telefono}")
                    invalidar_chat_equipo(telefono)
                    break

        if ultimo_error:
            logger.error("Modo equipo falló para %s: %s", telefono, ultimo_error)

    return MENSAJE_RESCATE


def _obtener_chat_equipo_con_modelo(telefono: str, nombre: str, modelo: str):
    clave_mem = f"{telefono}:{PROMPT_VERSION}:{modelo}"
    if clave_mem not in _memoria_equipo:
        _memoria_equipo[clave_mem] = _crear_chat_equipo(telefono, nombre, modelo)
        _prompt_version_equipo[telefono] = PROMPT_VERSION
        _modelo_activo_equipo[telefono] = modelo
    return _memoria_equipo[clave_mem]


def invalidar_chat_equipo(telefono: str):
    for k in list(_memoria_equipo.keys()):
        if k.startswith(f"{telefono}:"):
            _memoria_equipo.pop(k, None)
    _prompt_version_equipo.pop(telefono, None)
    _modelo_activo_equipo.pop(telefono, None)
