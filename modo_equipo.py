"""Modo Pro (antes «modo equipo») — Alessia como asistente IA completa tras contraseña."""
from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import TimeoutError as FuturesTimeout

from google.genai import types

import config
import storage
from conversacion import (
    clave_conversacion_equipo,
    historial_para_gemini,
    registrar_turno_equipo,
    texto_desde_contenido,
)
from gemini_runtime import get_genai_client, send_message_con_timeout
from observability import registrar_fallo_gemini
from tools import obtener_contexto_fecha_actual

logger = logging.getLogger(__name__)

PROMPT_VERSION = "equipo-2026-07-31a"
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
        # Nombre actual
        "modo pro",
        "#pro",
        "acceso pro",
        "entrar a modo pro",
        "quiero modo pro",
        "acceso al modo pro",
        # Alias legacy (siguen funcionando)
        "modo equipo",
        "#equipo",
        "acceso equipo",
        "equipo inpulso",
        "entrar al equipo",
        "quiero entrar al equipo",
        "acceso al equipo",
    }
)
_COMANDOS_SALIR = frozenset(
    {
        "salir pro",
        "salir modo pro",
        "cerrar pro",
        "cerrar modo pro",
        # Alias legacy
        "salir equipo",
        "salir modo equipo",
        "cerrar equipo",
    }
)


def _cliente():
    return get_genai_client()


def _nombre_miembro(telefono: str) -> str:
    if sesion_equipo_activa(telefono):
        return storage.obtener_nombre_equipo_sesion(telefono)
    conocido = config.identificar_miembro_equipo(telefono)
    return conocido or "Equipo Inpulso"


def _es_solicitud_acceso_equipo(texto: str) -> bool:
    """True solo si piden entrar a Modo Pro (no si solo lo mencionan)."""
    norm = (texto or "").strip().lower().replace("_", " ")
    norm = re.sub(r"\s+", " ", norm)
    if norm in _COMANDOS_ENTRADA:
        return True
    # Frases largas tipo "estábamos en modo pro sincronizando…" NO son pedido de acceso
    if len(norm) > 36:
        return False
    inicios = (
        "modo pro",
        "modo equipo",
        "#pro",
        "#equipo",
        "acceso pro",
        "acceso equipo",
        "acceso al modo pro",
        "acceso al equipo",
        "entrar a modo pro",
        "entrar al equipo",
        "quiero modo pro",
        "quiero entrar al equipo",
        "equipo inpulso",
    )
    return any(norm == i or norm.startswith(i + " ") or norm.startswith(i + ",") for i in inicios)


def _instrucciones_equipo(nombre: str) -> str:
    return f"""
Eres *Alessia*, asistente de inteligencia artificial del equipo interno de Inpulso 43.
Estás hablando con *{nombre}* (uso interno — NO es un paciente).
Estás en *Modo Pro* (asistente completo).

IDENTIDAD (CRÍTICO — SIEMPRE):
- Tu nombre es *Alessia* y solo Alessia. Preséntate siempre así.
- Puedes reconocer que eres una IA si te preguntan; con pacientes nunca lo harías, pero aquí es Modo Pro.
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
- Modo actual: *Modo Pro* — IA completa sin restricciones de recepción.
- Versión de instrucciones: {PROMPT_VERSION}.

NATURALEZA DE ESTE MODO:
- Capacidades completas de asistente IA avanzado: razonamiento, redacción, análisis, síntesis, lluvia de ideas,
  código, tablas, planes de trabajo, emails, guiones, etc.
- Responde en el idioma del usuario (por defecto español de México).
- Tono: colega profesional, claro y útil; natural, sin teatralidad.
- PROHIBIDO empezar mensajes con "Ay", "¡Ay", "¡Ay, [nombre]!" u exclamaciones fingidas — suena falso.
- No repitas el nombre del usuario al inicio de cada mensaje; entra directo al contenido.
- FORMATO WHATSAPP (diseño limpio): negritas con *texto* (nunca **texto**); listas con • o números;
  PROHIBIDO bullets con asterisco; negritas solo en títulos/claves; sin saturar de símbolos.

ARCHIVOS Y DOCUMENTOS (CRÍTICO):
- Si envían imagen, PDF, audio, video o documento: léelo/analízalo por completo.
- Extrae información, resume, reestructura, corrige, da formato, propone esquemas o entregables listos.
- Si piden "dame esto en bullets / tabla / correo / guion", hazlo directamente.
- Si el archivo es ilegible, dilo y pide otro formato o más contexto.
- PDFs: el sistema YA intenta extraer el texto y guardarlo en la base de conocimiento para pacientes.
  Si el mensaje trae "[Sistema: PDF guardado automáticamente…]", confirma qué quedó guardado (tema + resumen)
  y NO digas que lo vas a guardar: ya está. Si falló el auto-guardado, llama *guardar_conocimiento_pacientes*.

TRABAJO CON INPULSO:
- Conoces que Inpulso 43 es clínica de psicología, nutrición, medicina y talleres en Zapopan.
- Sitio: {config.CLINICA_WEB_URL}
- Puedes ayudar con copy, protocolos internos, ideas de talleres, organización — sin inventar datos
  clínicos oficiales que no te hayan dado.
- Datos de pacientes: trata como confidenciales; no los reutilices fuera del contexto del pedido.

ENSEÑAR A ALESSIA PARA PACIENTES (CRÍTICO):
- Si te dan información que los *pacientes* deben saber (precios, fechas de talleres, horarios,
  políticas, cupos, promociones), SIEMPRE llama la herramienta *guardar_conocimiento_pacientes*
  con un tema corto y el contenido completo. Ejemplo: tema="taller heridas", contenido="Cuesta $2500...".
- Habla natural: si dicen "el taller de heridas cuesta X", tú guardas y confirmas que quedó.
- PDFs del equipo con info de pacientes: prioriza el auto-guardado del sistema; solo usa la herramienta
  si el auto-guardado falló o si te pegan texto (sin PDF).
- Para ver lo guardado: *listar_conocimiento_pacientes*. Para quitar: *borrar_conocimiento_pacientes* con el ID.
- HOJA HERIDAS: si piden "actualiza la hoja", "sincroniza inscritos", "llena Heridas_Cupo",
  "sincroniza la hoja de heridas" o similar, llama *sincronizar_panel_heridas*.
  Confirma el resultado (cuántos inscritos/interesados y el link).
  Esto solo está disponible en *Modo Pro*.
- HOJA ANALYTICS: si piden "sincroniza la hoja de analytics" o similar, llama *sincronizar_panel_analytics*.
- Eso se sincroniza a Google Sheets (hoja Conocimiento) para Alessandro/desarrollo.

LÍMITES SANOS:
- No sustituyes criterio clínico ni legal; sugiere revisión humana cuando aplique.
- Si piden algo enorme, entrégalo por partes claras.

Eres la herramienta de productividad del equipo en *Modo Pro*. Sé excelente.
"""


def _crear_chat_equipo(telefono: str, nombre: str, modelo: str):
    from conocimiento import (
        borrar_conocimiento_pacientes,
        guardar_conocimiento_pacientes,
        listar_conocimiento_pacientes,
    )
    from heridas_sheet import sincronizar_panel_heridas
    from analytics import sincronizar_panel_analytics

    conv = clave_conversacion_equipo(telefono)
    return _cliente().chats.create(
        model=modelo,
        history=historial_para_gemini(conv),
        config=types.GenerateContentConfig(
            system_instruction=_instrucciones_equipo(nombre),
            temperature=config.EQUIPO_GEMINI_TEMPERATURE,
            tools=[
                guardar_conocimiento_pacientes,
                listar_conocimiento_pacientes,
                borrar_conocimiento_pacientes,
                sincronizar_panel_heridas,
                sincronizar_panel_analytics,
            ],
        ),
    )


def envolver_mensaje_equipo(telefono: str, contenido):
    """Contexto mínimo para Modo Pro — sin reglas de paciente."""
    nombre = _nombre_miembro(telefono)
    ctx = (
        obtener_contexto_fecha_actual()
        + f"[Sistema: MODO PRO — {nombre}. Asistente IA completa.]\n"
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
    """True si hay sesión Modo Pro activa (nombre interno legacy)."""
    return sesion_equipo_activa(telefono)


def _clave_correcta(texto: str) -> bool:
    from seguridad import verificar_clave

    secreto = config.secreto_modo_equipo()
    if not secreto:
        return False
    return verificar_clave(texto.strip(), secreto)


def _mensaje_pedir_clave() -> str:
    return (
        "🔐 *Modo Pro*\n\n"
        "Envía la contraseña de acceso (solo personal de Inpulso).\n"
        "Para cancelar, escribe *SALIR PRO*."
    )


def _mensaje_acceso_ok(nombre: str) -> str:
    horas = config.EQUIPO_SESION_HORAS
    if horas >= 24:
        vigencia = f"{max(1, horas // 24)} días"
    else:
        vigencia = f"{horas} h"
    return (
        f"✅ *Modo Pro* listo por *{vigencia}*, {nombre}.\n\n"
        "Las hojas *Heridas* y *Analytics* se actualizan *solas cada minuto* "
        "(ya no hace falta pedir sync por aquí).\n"
        "Para salir: *SALIR PRO*"
    )


def procesar_preflight_equipo(telefono: str, texto: str) -> str | None:
    """
    Maneja comandos de acceso a Modo Pro.
    - str: mensaje ya resuelto para enviar al usuario (no pasar a IA)
    - MARCADOR_IA: sesión activa, continuar con IA de Modo Pro
    - None: no aplica, flujo paciente normal
    """
    if not config.ENABLE_MODO_EQUIPO:
        return None

    limpio = (texto or "").strip()
    norm = limpio.lower().replace("_", " ")

    if norm in _COMANDOS_SALIR:
        if sesion_equipo_activa(telefono) or storage.esperando_clave_equipo(telefono):
            cerrar_sesion_equipo(telefono)
            return (
                "Listo, salí de *Modo Pro*. Vuelvo a recepción 😊\n"
                "Para entrar de nuevo escribe *MODO PRO*."
            )
        # No caer a recepción/taller: el equipo escribió SALIR PRO a propósito
        return (
            "No había una sesión de *Modo Pro* activa.\n"
            "Para entrar escribe *MODO PRO*."
        )

    if sesion_equipo_activa(telefono):
        storage.renovar_sesion_equipo(telefono, config.EQUIPO_SESION_HORAS)
        if norm in _COMANDOS_ENTRADA or _es_solicitud_acceso_equipo(limpio):
            return (
                "Ya estás en *Modo Pro* ✅ ¿En qué te ayudo?\n"
                "Para salir escribe *SALIR PRO*."
            )
        return MARCADOR_IA

    if storage.esperando_clave_equipo(telefono):
        if storage.equipo_clave_bloqueada(
            telefono,
            config.EQUIPO_CLAVE_MAX_INTENTOS,
            config.EQUIPO_CLAVE_BLOQUEO_MINUTOS,
        ):
            return (
                "Demasiados intentos fallidos 🔒 El acceso a *Modo Pro* está bloqueado unos minutos. "
                "Intenta más tarde o escribe *SALIR PRO*."
            )
        if not config.secreto_modo_equipo():
            storage.cancelar_esperando_clave_equipo(telefono)
            return (
                "*Modo Pro* no está configurado en el servidor todavía. "
                "Avísale a Alessandro."
            )
        if _clave_correcta(limpio):
            storage.resetear_intentos_clave_equipo(telefono)
            nombre = _nombre_miembro(telefono)
            activar_sesion_equipo(telefono, nombre)
            invalidar_chat_equipo(telefono)
            return _mensaje_acceso_ok(nombre)
        storage.registrar_intento_clave_equipo_fallido(telefono)
        storage.cancelar_esperando_clave_equipo(telefono)
        return (
            "Contraseña incorrecta 🔒 Sigo en modo recepción.\n"
            "Si eres del equipo, escribe *MODO PRO* e inténtalo de nuevo."
        )

    if _es_solicitud_acceso_equipo(limpio):
        if not config.secreto_modo_equipo():
            return (
                "*Modo Pro* aún no tiene contraseña configurada en el servidor. "
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
                    respuesta = send_message_con_timeout(
                        chat, contenido, timeout=timeout
                    )
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
            logger.error("Modo Pro falló para %s: %s", telefono, ultimo_error)

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
