"""Pipeline de entrada WhatsApp: intents, comandos, media (fuera de Flask)."""
from __future__ import annotations

import datetime
import logging
import re

import pytz
from google.genai import types

import config
import storage
from bienestar import comando_biblioteca, micro_ejercicio_para_texto
from chat import reiniciar_chat_paciente
from experiencia import (
    calcular_minutos_ruta,
    guardar_nota_ritual_cierre,
    guardar_prep_sesion,
    mensaje_mi_cita,
    procesar_boton_recordatorio,
    respuesta_seguimiento_nps,
)
from marca import contexto_blog_si_aplica
from tools import (
    agregar_lista_espera,
    eliminar_datos_arco,
    notificar_emergencia_paciente,
    notificar_llegada_paciente,
)
from whatsapp import descargar_media_whatsapp, enviar_mensaje_whatsapp

logger = logging.getLogger(__name__)


def manejar_privacidad_entrada(telefono: str, texto: str) -> str | None:
    """
    Consentimiento explícito (no silencioso).
    Retorna:
      - None: continuar flujo normal
      - "bloqueado": ya se respondió al usuario; no seguir con IA
    """
    from modo_equipo import sesion_equipo_activa

    if config.identificar_terapeuta(telefono) or sesion_equipo_activa(telefono):
        return None

    limpio = (texto or "").strip().upper().replace("_", " ")
    aceptaciones = {
        "ACEPTO",
        "ACEPTO PRIVACIDAD",
        "ACEPTO EL AVISO",
        "ACEPTO AVISO",
        "SI ACEPTO",
        "SÍ ACEPTO",
    }
    if limpio in aceptaciones or limpio.startswith("ACEPTO "):
        storage.registrar_consentimiento(telefono)
        enviar_mensaje_whatsapp(
            telefono,
            "Gracias 🙏 Guardé tu aceptación del aviso de privacidad. "
            "¿En qué te ayudo?",
        )
        return "bloqueado"

    if not storage.necesita_consentimiento(telefono):
        return None

    if not storage.aviso_privacidad_ya_enviado(telefono):
        storage.marcar_aviso_privacidad_enviado(telefono)
        enviar_mensaje_whatsapp(
            telefono,
            config.AVISO_PRIVACIDAD
            + "\n\nSi estás de acuerdo, responde *ACEPTO* para continuar.",
        )
        # No bloqueamos el resto del mensaje: puede ser su primera duda.
    return None


def _procesar_estados_whatsapp(datos: dict):
    """Registra entregas/fallos de mensajes salientes (statuses de Meta)."""
    for entry in datos.get("entry", []):
        for change in entry.get("changes", []):
            for status in change.get("value", {}).get("statuses", []):
                estado = status.get("status", "")
                msg_id = status.get("id", "")
                if estado == "failed":
                    errors = status.get("errors", [])
                    logger.error("WhatsApp falló msg=%s errors=%s", msg_id, errors)
                elif estado in ("delivered", "read"):
                    logger.debug("WhatsApp %s msg=%s", estado, msg_id)


def _extraer_texto_respuesta_boton(mensaje_info: dict) -> str | None:
    """Texto que envía WhatsApp al pulsar Quick Reply en plantilla."""
    tipo = mensaje_info.get("type")
    if tipo == "button":
        return mensaje_info.get("button", {}).get("text", "").strip() or None
    if tipo == "interactive":
        inter = mensaje_info.get("interactive", {})
        if inter.get("type") == "button_reply":
            return inter.get("button_reply", {}).get("title", "").strip() or None
    return None


def _manejar_boton_recordatorio(telefono: str, texto: str) -> bool:
    if config.identificar_terapeuta(telefono):
        return False
    respuesta = procesar_boton_recordatorio(telefono, texto)
    if not respuesta:
        return False
    enviar_mensaje_whatsapp(telefono, respuesta)
    logger.info("Botón recordatorio '%s' atendido para %s", texto[:40], telefono)
    return True


def _extraer_nombre_del_mensaje(texto: str) -> str | None:
    """Detecta presentación casual: 'me llamo X', 'soy X', 'mi nombre es X'."""
    patrones = [
        r"(?:me llamo|mi nombre es)\s+([A-Za-zÁÉÍÓÚáéíóúÑñ][A-Za-zÁÉÍÓÚáéíóúÑñ\s]{1,50})",
        r"^soy\s+([A-Za-zÁÉÍÓÚáéíóúÑñ][A-Za-zÁÉÍÓÚáéíóúÑñ\s]{1,50})$",
    ]
    texto_limpio = texto.strip()
    for patron in patrones:
        m = re.search(patron, texto_limpio, re.IGNORECASE)
        if m:
            nombre = " ".join(m.group(1).strip().split()[:4])
            if len(nombre) >= 2 and nombre.lower() not in (
                "alessia", "inpulso", "hola", "buenas", "buenos", "noches", "tardes", "dias",
            ):
                return nombre
    return None


def _extraer_mensajes_whatsapp(datos: dict):
    """Recorre todo el payload de Meta (puede traer varios mensajes)."""
    for entry in datos.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for mensaje in value.get("messages", []):
                yield mensaje


def preparar_contenido_mensaje(mensaje_info: dict):
    numero_remitente = mensaje_info["from"]
    tipo_mensaje = mensaje_info.get("type")

    texto_boton = _extraer_texto_respuesta_boton(mensaje_info)
    if texto_boton and _manejar_boton_recordatorio(numero_remitente, texto_boton):
        return None

    zona_mexico = pytz.timezone(config.ZONA_MEXICO)
    hora_exacta = datetime.datetime.now(zona_mexico).strftime("%Y-%m-%d %H:%M")
    texto_contexto = f"[Sistema: Mensaje recibido el {hora_exacta}] "

    if tipo_mensaje == "text":
        texto_paciente = mensaje_info["text"]["body"].strip()

        from modo_equipo import MARCADOR_IA, procesar_preflight_equipo, sesion_equipo_activa

        preflight = procesar_preflight_equipo(numero_remitente, texto_paciente)
        if preflight is not None and preflight != MARCADOR_IA:
            enviar_mensaje_whatsapp(numero_remitente, preflight)
            return None
        if preflight == MARCADOR_IA or sesion_equipo_activa(numero_remitente):
            return texto_paciente

        es_terapeuta = config.identificar_terapeuta(numero_remitente)

        if es_terapeuta:
            return texto_contexto + f"[Modo staff: {es_terapeuta}]\n" + texto_paciente

        if _manejar_boton_recordatorio(numero_remitente, texto_paciente):
            return None

        nombre_detectado = _extraer_nombre_del_mensaje(texto_paciente)
        if nombre_detectado:
            storage.guardar_nombre_casual(numero_remitente, nombre_detectado)

        if storage.es_primera_vez(numero_remitente):
            storage.marcar_no_primera_vez(numero_remitente)
            storage.obtener_o_crear_codigo_referido(numero_remitente)
            hora = datetime.datetime.now(zona_mexico).hour
            if hora < 12:
                saludo_hora = "buenos días"
            elif hora < 19:
                saludo_hora = "buenas tardes"
            else:
                saludo_hora = "buenas noches"
            conocido = storage.primer_nombre(numero_remitente)
            if conocido:
                extra = (
                    f"Paciente recurrente (nombre guardado: {conocido}). "
                    f"Salúdalo por su nombre. NO preguntes cómo se llama."
                )
            else:
                extra = (
                    "Paciente nuevo sin nombre guardado. "
                    "NO pidas nombre para charlar; solo al agendar o inscribir a taller."
                )
            return (
                texto_contexto
                + f"[Sistema: PRIMER CONTACTO EN SISTEMA — Saluda con '{saludo_hora}', "
                f"preséntate como 'Alessia, de Inpulso 43'. {extra} "
                f"Tono MUY cálido y humano, con emojis (😊 ✨). PROHIBIDO ser cortante, seca o fría. "
                f"PROHIBIDO decir virtual, IA o bot. "
                f"Si el mensaje incluye una pregunta, respóndela en el mismo mensaje con cariño.]\n"
                + texto_paciente
            )

        texto_lower = texto_paciente.lower()

        cmd = comando_biblioteca(texto_paciente)
        if cmd:
            if texto_paciente.upper() == "CRISIS":
                notificar_emergencia_paciente(numero_remitente, "Comando CRISIS")
            enviar_mensaje_whatsapp(numero_remitente, cmd)
            if texto_paciente.upper() == "CRISIS":
                return None
            return texto_contexto + f"[Sistema: Comando {texto_paciente.upper()} enviado.]\n" + texto_paciente

        texto_cmd = texto_paciente.strip().upper().replace("_", " ")
        if texto_cmd in ("MI CITA", "MICITA", "MIS CITAS"):
            enviar_mensaje_whatsapp(numero_remitente, mensaje_mi_cita(numero_remitente))
            return None

        if storage.obtener_ritual_pendiente(numero_remitente) and len(texto_paciente) > 3:
            guardar_nota_ritual_cierre(numero_remitente, texto_paciente)
            enviar_mensaje_whatsapp(
                numero_remitente,
                "💙 Guardé tu reflexión. Es solo tuya — gracias por compartirla.",
            )
            return None

        if storage.obtener_prep_pendiente(numero_remitente) and len(texto_paciente) > 5:
            guardar_prep_sesion(numero_remitente, texto_paciente, "")
            return (
                texto_contexto
                + "[Sistema: Prep de sesión guardado para el terapeuta. Agradece con calidez.]\n"
                + texto_paciente
            )

        if texto_paciente.upper() in ("ACTIVAR FRASE", "FRASE DEL DIA", "FRASE DEL DÍA"):
            storage.activar_frase_dia(numero_remitente, True)
            enviar_mensaje_whatsapp(
                numero_remitente,
                "☀️ Listo — te enviaré una frase de bienestar cada mañana (8 am). "
                "Escribe *DESACTIVAR FRASE* cuando quieras pausarlo.",
            )
            return None

        if texto_paciente.upper() == "DESACTIVAR FRASE":
            storage.activar_frase_dia(numero_remitente, False)
            enviar_mensaje_whatsapp(numero_remitente, "Entendido, pausé las frases matutinas 😊")
            return None

        ref_match = re.search(r"INPULSO-[A-F0-9]{6}", texto_paciente.upper())
        if ref_match:
            from tools import registrar_codigo_referido
            resultado = registrar_codigo_referido(numero_remitente, ref_match.group(0))
            return texto_contexto + f"[Sistema: {resultado}]\n" + texto_paciente

        escala_match = re.match(r"^\s*(\d{1,2})\s*$", texto_paciente)
        if escala_match:
            escala = int(escala_match.group(1))
            if 1 <= escala <= 10:
                if storage.obtener_nps_pendiente(numero_remitente):
                    enviar_mensaje_whatsapp(
                        numero_remitente,
                        respuesta_seguimiento_nps(numero_remitente, escala),
                    )
                    return None
                storage.guardar_checkin_emocional(numero_remitente, escala)
                return (
                    texto_contexto
                    + f"[Sistema: Check-in emocional registrado ({escala}/10). "
                    f"Agradece con calidez; si es bajo (1-4), ofrece apoyo sin alarmar.]\n"
                    + texto_paciente
                )

        blog_ctx = contexto_blog_si_aplica(texto_paciente)

        if any(p in texto_lower for p in config.PALABRAS_ORIENTACION_INICIAL):
            return (
                texto_contexto
                + blog_ctx
                + "[Sistema: ORIENTACIÓN INICIAL — El paciente no sabe qué especialista necesita. "
                "PROHIBIDO recomendar Sara ni pedir nombre completo todavía. "
                "Pregunta con calidez qué síntomas o situación le preocupa. "
                "Luego: psicología → Sara Rosales; nutrición → Gabriela Sánchez; "
                "medicina → registrar_escalacion_humana y avisar que recepción contactará.]\n"
                + texto_paciente
            )

        ejercicio = micro_ejercicio_para_texto(texto_paciente)
        if ejercicio and any(p in texto_lower for p in config.PALABRAS_ANSIEDAD):
            enviar_mensaje_whatsapp(numero_remitente, ejercicio)

        if texto_paciente.upper() == "ELIMINAR DATOS":
            resultado = eliminar_datos_arco(numero_remitente)
            reiniciar_chat_paciente(numero_remitente)
            enviar_mensaje_whatsapp(
                numero_remitente,
                "Tus datos han sido eliminados de nuestros sistemas automatizados. "
                "Si necesitas confirmación escrita, contacta a recepción. 🙏",
            )
            logger.info("ARCO eliminación: %s — %s", numero_remitente, resultado[:120])
            return None

        from escalacion import es_solicitud_humano, mensaje_confirmacion_escalacion
        from tools import escalar_a_recepcion

        if es_solicitud_humano(texto_paciente):
            estado = escalar_a_recepcion(
                numero_remitente,
                f"Paciente solicitó humano: {texto_paciente[:180]}",
            )
            enviar_mensaje_whatsapp(
                numero_remitente,
                mensaje_confirmacion_escalacion(
                    aviso_enviado=bool(estado.get("whatsapp_ok")),
                    recepcion_configurada=bool(estado.get("recepcion_configurada")),
                ),
            )
            logger.info(
                "Escalación humana por %s — wa_ok=%s recepcion=%s",
                numero_remitente,
                estado.get("whatsapp_ok"),
                estado.get("recepcion_configurada"),
            )
            return None

        if texto_paciente.strip().upper().startswith("HISTORIA"):
            nombre = storage.primer_nombre(numero_remitente) or "Paciente WhatsApp"
            agregar_lista_espera(
                nombre,
                numero_remitente,
                "Sanando tus heridas del pasado",
                "Lista de espera taller",
            )
            enviar_mensaje_whatsapp(
                numero_remitente,
                "Listo ✨ Te anoté en la lista de espera del taller "
                "*Sanando tus heridas del pasado*. En cuanto haya lugar te avisamos por aquí.",
            )
            logger.info("Lista espera HISTORIA: %s", numero_remitente)
            return None

        if any(palabra in texto_lower for palabra in config.PALABRAS_PRIVACIDAD):
            return (
                texto_contexto
                + "[Sistema: Pregunta sobre privacidad. Responde con tono humano y breve. "
                f"Puedes indicar {config.AVISO_PRIVACIDAD_URL} si lo piden. "
                "NO envíes el bloque automático de aviso de privacidad.]\n"
                + texto_paciente
            )

        if any(p in texto_lower for p in config.PALABRAS_LLEGADA):
            notificar_llegada_paciente(numero_remitente)
            return (
                texto_contexto
                + "[Sistema: Paciente indica que YA LLEGÓ — terapeuta notificado automáticamente. "
                "Confirma con calidez. NO llames notificar_llegada_paciente otra vez.]\n"
                + texto_paciente
            )

        if any(p in texto_lower for p in config.PALABRAS_EMERGENCIA):
            notificar_emergencia_paciente(numero_remitente, texto_paciente[:400])
            return (
                texto_contexto
                + "[Sistema: EMERGENCIA detectada — terapeuta y recepción alertados. "
                "Indica 911 si hay riesgo inmediato. NO llames notificar_emergencia_paciente otra vez.]\n"
                + texto_paciente
            )

        if storage.obtener_reagendar_pendiente(numero_remitente):
            return (
                texto_contexto
                + blog_ctx
                + "[Sistema: El paciente pidió reagendar tras un recordatorio. "
                "Usa reagendar_cita_atomica cuando elija fecha/hora; no canceles antes de agendar.]\n"
                + texto_paciente
            )

        return texto_contexto + blog_ctx + texto_paciente

    if tipo_mensaje == "location":
        lat = mensaje_info["location"]["latitude"]
        lng = mensaje_info["location"]["longitude"]
        storage.guardar_ubicacion(numero_remitente, lat, lng)
        minutos = calcular_minutos_ruta(numero_remitente)
        if minutos:
            salir = max(minutos - 10, 5)
            enviar_mensaje_whatsapp(
                numero_remitente,
                f"📍 Ubicación guardada. Con el tráfico actual, tu ruta a Inpulso 43 "
                f"es de ~{minutos} min. Si tienes cita pronto, te sugiero salir en "
                f"*{salir} minutos*.",
            )
        return (
            texto_contexto
            + f"[El paciente envió su ubicación {lat},{lng}]. "
            "Usa obtener_ruta_inpulso y responde el tiempo."
        )

    if tipo_mensaje in ["image", "video", "audio", "voice", "document"]:
        tipo_clave = "voice" if tipo_mensaje == "voice" else tipo_mensaje
        media_id = mensaje_info[tipo_clave]["id"]
        file_bytes, mime_type = descargar_media_whatsapp(media_id)

        if file_bytes:
            caption = mensaje_info.get(tipo_clave, {}).get("caption", "")
            from modo_equipo import sesion_equipo_activa

            if sesion_equipo_activa(numero_remitente):
                from modo_equipo import _nombre_miembro

                miembro_equipo = _nombre_miembro(numero_remitente)
                if tipo_mensaje in ("audio", "voice"):
                    texto_descriptivo = (
                        "NOTA DE VOZ del equipo Inpulso. Transcribe y responde con lo que necesiten."
                    )
                else:
                    texto_descriptivo = (
                        f"Archivo de trabajo ({tipo_mensaje}) enviado por {miembro_equipo}. "
                        "Analízalo a fondo: extrae, resume, estructura o transforma según el pedido."
                    )
                if caption:
                    texto_descriptivo += f" Instrucciones del equipo: {caption}"
                return [
                    types.Part(inline_data=types.Blob(data=file_bytes, mime_type=mime_type)),
                    types.Part(text=texto_descriptivo),
                ]
            if tipo_mensaje in ("audio", "voice"):
                texto_descriptivo = (
                    "NOTA DE VOZ del paciente. Escucha/transcribe el audio y responde "
                    "al contenido de forma natural. Si no entiendes el audio, pide "
                    "amablemente que lo repita por texto."
                )
            else:
                texto_descriptivo = f"Archivo tipo {tipo_mensaje}."
            if caption:
                texto_descriptivo += f" Texto adjunto: {caption}"
            instruccion_pago = ""
            if tipo_mensaje in ("image", "document"):
                from prompt_pagos import instruccion_comprobante_pago

                instruccion_pago = " " + instruccion_comprobante_pago(
                    telefono_paciente=numero_remitente
                )
            return [
                types.Part(inline_data=types.Blob(data=file_bytes, mime_type=mime_type)),
                types.Part(text=(texto_contexto + texto_descriptivo + instruccion_pago)),
            ]
        return texto_contexto + "Error al descargar archivo."

    return None

