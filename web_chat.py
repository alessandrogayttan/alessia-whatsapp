"""Chat web de Alessia — mismo cerebro que WhatsApp, canal HTTP aparte."""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import uuid

from concurrent.futures import TimeoutError as FuturesTimeout

from google.genai import types

import config
import storage
from conversacion import (
    clave_conversacion_web,
    historial_para_gemini,
    registrar_turno_web,
    vincular_conversacion_web,
)
from conocimiento import buscar_conocimiento_clinica
from gemini_runtime import get_genai_client, send_message_con_timeout
from observability import registrar_fallo_gemini
from tools import (
    actualizar_pago_paciente,
    agendar_cita,
    agregar_lista_espera,
    buscar_cita_paciente,
    buscar_conocimiento_inpulso,
    calcular_gasto_combustible,
    cambiar_servicio_cita,
    cancelar_cita_paciente,
    confirmar_pago_comprobante,
    consultar_agenda,
    consultar_mis_citas,
    consultar_precios_y_servicios,
    consultar_sitio_inpulso,
    consultar_talleres_y_servicios,
    guardar_nota_ritual_cierre,
    guardar_prep_sesion,
    notificar_emergencia_paciente,
    notificar_llegada_paciente,
    obtener_contexto_citas_paciente,
    obtener_contexto_fecha_actual,
    obtener_contexto_perfil_paciente,
    obtener_mi_codigo_referido,
    obtener_ruta_inpulso,
    recordar_nombre_paciente,
    reagendar_cita_atomica,
    reagendar_cita_inteligente,
    registrar_escalacion_humana,
    registrar_interes_taller,
    registrar_paciente_taller,
    registrar_solicitud_facturacion,
    validar_fecha_cita,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "web-2026-07-22a"
_memoria_web: dict[str, object] = {}
_prompt_version_web: dict[str, str] = {}
_cerrojos_web: dict[str, threading.Lock] = {}

MENSAJE_RESCATE = (
    "Perdóname, tuve un pequeño tropiezo técnico 🙈 "
    "¿Me repites tu mensaje? Estoy aquí contigo."
)

_SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.I,
)


def _instruccion_comprobante() -> str:
    from prompt_pagos import instruccion_comprobante_web

    return instruccion_comprobante_web()


def _id_operaciones(session_id: str, telefono: str | None) -> str:
    return telefono or f"web:{session_id}"


def _construir_instrucciones_web(
    session_id: str,
    telefono: str | None,
    nombre: str | None,
) -> str:
    """Mismo prompt de pacientes WhatsApp + ajustes mínimos del canal web."""
    from chat import _construir_instrucciones

    id_ops = _id_operaciones(session_id, telefono)
    base = _construir_instrucciones(id_ops)
    wa = config.WHATSAPP_PACIENTES_URL or "WhatsApp de Inpulso 43"
    unificado = (
        "Su historial está unificado con WhatsApp."
        if telefono
        else "Cuando den su WhatsApp (10 dígitos MX), el historial se unifica con ese número."
    )

    return (
        base
        + f"""

CANAL WEB (mismas reglas e información que WhatsApp):
- Atiendes el chat en vivo de {config.CLINICA_WEB_URL}. Capacidad de información = WhatsApp.
- PROHIBIDO responder solo con "déjame revisar", "un momentito", "busco en recursos" o similares
  sin entregar la información concreta en ESE mismo mensaje.
- Si [WEB VIVA], [RAG] o el catálogo del system prompt ya traen el dato (talleres, club de lectura,
  precios, equipo), RESPONDE YA con esos datos. No digas que vas a buscar.
- Si aún falta detalle: llama consultar_sitio_inpulso, buscar_conocimiento_inpulso,
  buscar_conocimiento_clinica o consultar_talleres_y_servicios ANTES de responder, y luego da la info.
- SÍ puedes recibir imágenes/comprobantes; usa confirmar_pago_comprobante si aplica.
- Antes de agendar o inscribir sin WhatsApp vinculado, pídelo con calidez.
- *MI CITA*, recordatorios automáticos y *HABLAR CON PERSONA* son más cómodos por WhatsApp: {wa}
- Teléfono sesión: {telefono or "(aún no)"}. Nombre: {nombre or "(aún no)"}. {unificado}
"""
    )


def _herramientas_web():
    """Misma batería de herramientas que pacientes en WhatsApp."""
    return [
        consultar_agenda,
        consultar_mis_citas,
        validar_fecha_cita,
        notificar_llegada_paciente,
        notificar_emergencia_paciente,
        agendar_cita,
        cancelar_cita_paciente,
        cambiar_servicio_cita,
        buscar_cita_paciente,
        obtener_ruta_inpulso,
        calcular_gasto_combustible,
        consultar_precios_y_servicios,
        consultar_sitio_inpulso,
        buscar_conocimiento_inpulso,
        buscar_conocimiento_clinica,
        consultar_talleres_y_servicios,
        registrar_paciente_taller,
        registrar_interes_taller,
        confirmar_pago_comprobante,
        actualizar_pago_paciente,
        agregar_lista_espera,
        obtener_mi_codigo_referido,
        recordar_nombre_paciente,
        reagendar_cita_inteligente,
        reagendar_cita_atomica,
        guardar_prep_sesion,
        guardar_nota_ritual_cierre,
        registrar_solicitud_facturacion,
        registrar_escalacion_humana,
    ]


def _memoria_clave(session_id: str, telefono: str | None) -> str:
    return f"{clave_conversacion_web(session_id, telefono)}:{PROMPT_VERSION}"


def _invalidar_memoria_web(session_id: str):
    for k in list(_memoria_web.keys()):
        if session_id in k:
            _memoria_web.pop(k, None)
    _prompt_version_web.pop(session_id, None)


def _obtener_chat_web(session_id: str, telefono: str | None, nombre: str | None):
    clave = _memoria_clave(session_id, telefono)
    conv_clave = clave_conversacion_web(session_id, telefono)
    if clave not in _memoria_web or _prompt_version_web.get(conv_clave) != PROMPT_VERSION:
        _memoria_web[clave] = get_genai_client().chats.create(
            model="gemini-2.5-flash",
            history=historial_para_gemini(conv_clave),
            config=types.GenerateContentConfig(
                system_instruction=_construir_instrucciones_web(
                    session_id, telefono, nombre
                ),
                tools=_herramientas_web(),
            ),
        )
        _prompt_version_web[conv_clave] = PROMPT_VERSION
    return _memoria_web[clave]


def _gemini_send_message(chat, contenido, timeout: int | None = None):
    return send_message_con_timeout(
        chat, contenido, timeout=timeout or config.GEMINI_PACIENTE_TIMEOUT
    )


def _normalizar_telefono_mexico(texto: str) -> str | None:
    digits = re.sub(r"\D", "", texto)
    if len(digits) == 10:
        return "52" + digits
    if digits.startswith("521") and len(digits) == 13:
        return "52" + digits[3:]
    if digits.startswith("52") and len(digits) == 12:
        return digits
    return None


def _extraer_telefono_de_mensaje(texto: str) -> str | None:
    for candidato in re.findall(r"\+?[\d\s\-()]{10,18}", texto):
        normalizado = _normalizar_telefono_mexico(candidato)
        if normalizado:
            return normalizado
    return None


def envolver_mensaje_web(
    session_id: str,
    telefono: str | None,
    nombre: str | None,
    mensaje: str,
) -> str:
    ctx = obtener_contexto_fecha_actual()
    ctx += f"[Sistema: CANAL WEB — sesión {session_id}]\n"
    if telefono:
        ctx += "[Sistema: Historial unificado con WhatsApp de este número.]\n"
        ctx += obtener_contexto_perfil_paciente(telefono)
        ctx += obtener_contexto_citas_paciente(telefono)
    else:
        ctx += (
            "[Sistema: Pide WhatsApp antes de agendar. Al darlo, se unifica el historial.]\n"
        )
    if config.ENABLE_INPULSO_WEB_LIVE:
        from inpulso_web_live import obtener_contexto_web_en_vivo

        ctx += obtener_contexto_web_en_vivo(mensaje)
    if config.ENABLE_INPULSO_RAG:
        from inpulso_rag import contexto_rag_para_mensaje

        ctx += contexto_rag_para_mensaje(mensaje)
    return ctx + mensaje


def _construir_contenido_multimodal(
    session_id: str,
    telefono: str | None,
    nombre: str | None,
    mensaje: str,
    imagen_bytes: bytes | None,
    mime_type: str,
):
    if not imagen_bytes:
        return envolver_mensaje_web(session_id, telefono, nombre, mensaje)

    partes = []
    envuelto = envolver_mensaje_web(
        session_id, telefono, nombre, mensaje or "(imagen enviada)"
    )
    partes.append(types.Part(text=envuelto))
    partes.append(
        types.Part(inline_data=types.Blob(data=imagen_bytes, mime_type=mime_type))
    )
    if mime_type.startswith("image/") or mime_type == "application/pdf":
        partes.append(types.Part(text=_instruccion_comprobante()))
    return partes


def nueva_sesion_web() -> str:
    session_id = str(uuid.uuid4())
    storage.crear_sesion_web(session_id)
    return session_id


def sesion_valida(session_id: str) -> bool:
    return bool(_SESSION_ID_RE.match(session_id or ""))


def _vincular_telefono_si_aplica(session_id: str, mensaje: str, sesion: dict) -> str | None:
    telefono = sesion.get("telefono_vinculado")
    if telefono:
        return telefono
    detectado = _extraer_telefono_de_mensaje(mensaje)
    if detectado:
        storage.actualizar_sesion_web(session_id, telefono=detectado)
        vincular_conversacion_web(session_id, detectado)
        _invalidar_memoria_web(session_id)
        return detectado
    return None


def procesar_mensaje_web(
    session_id: str,
    mensaje: str,
    *,
    imagen_bytes: bytes | None = None,
    mime_type: str = "image/jpeg",
) -> str:
    if not config.ENABLE_WEB_CHAT:
        raise RuntimeError("Chat web desactivado")
    if not sesion_valida(session_id):
        raise ValueError("Sesión inválida")

    tiene_imagen = bool(imagen_bytes)
    mensaje = (mensaje or "").strip()
    if not mensaje and not tiene_imagen:
        raise ValueError("Mensaje vacío")
    if len(mensaje) > 4000:
        raise ValueError("Mensaje inválido")

    sesion = storage.obtener_sesion_web(session_id)
    if not sesion:
        raise ValueError("Sesión no encontrada")

    telefono = _vincular_telefono_si_aplica(session_id, mensaje, sesion) or sesion.get(
        "telefono_vinculado"
    )
    nombre = sesion.get("nombre")

    if session_id not in _cerrojos_web:
        _cerrojos_web[session_id] = threading.Lock()

    registro_usuario = mensaje or "[imagen/comprobante enviado]"

    from respuesta_fiable import asegurar_respuesta_util, intentar_respuesta_catalogo

    # Preguntas claras de catálogo: respuesta inmediata (igual en WhatsApp)
    if not tiene_imagen:
        fijo = intentar_respuesta_catalogo(mensaje)
        if fijo:
            storage.actualizar_sesion_web(session_id)
            registrar_turno_web(session_id, telefono, registro_usuario, fijo)
            return fijo

    with _cerrojos_web[session_id]:
        import tools as tools_ctx

        tools_ctx._telefono_contexto = _id_operaciones(session_id, telefono)
        try:
            chat = _obtener_chat_web(session_id, telefono, nombre)
            contenido = _construir_contenido_multimodal(
                session_id, telefono, nombre, mensaje, imagen_bytes, mime_type
            )
            for intento in range(2):
                try:
                    respuesta = _gemini_send_message(chat, contenido)
                    texto = (getattr(respuesta, "text", None) or "").strip()
                    if texto:

                        def _regen(msg):
                            r = _gemini_send_message(chat, msg)
                            return (getattr(r, "text", None) or "").strip()

                        texto = asegurar_respuesta_util(
                            mensaje, texto, regenerar=_regen
                        )
                        if not texto:
                            continue
                        storage.actualizar_sesion_web(session_id)
                        registrar_turno_web(session_id, telefono, registro_usuario, texto)
                        return texto
                except FuturesTimeout:
                    logger.error("Timeout Gemini web %s intento %s", session_id, intento + 1)
                    registrar_fallo_gemini(f"web:{session_id}")
                    if intento == 0:
                        time.sleep(2)
                        continue
                except Exception as e:
                    logger.exception("Error Gemini web %s: %s", session_id, e)
                    registrar_fallo_gemini(f"web:{session_id}")
                    if intento == 0:
                        time.sleep(2)
                        continue
                    break
        finally:
            tools_ctx._telefono_contexto = None

    storage.actualizar_sesion_web(session_id)
    return MENSAJE_RESCATE


def hash_ip(ip: str) -> str:
    return hashlib.sha256(f"{ip}:web-chat".encode()).hexdigest()[:32]
