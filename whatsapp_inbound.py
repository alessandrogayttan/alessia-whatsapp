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
    """Compat no-op: ya no empujamos aviso ni pedimos ACEPTO."""
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


def _extraer_id_boton_interactive(mensaje_info: dict) -> str | None:
    if mensaje_info.get("type") != "interactive":
        return None
    inter = mensaje_info.get("interactive", {}) or {}
    if inter.get("type") != "button_reply":
        return None
    return (inter.get("button_reply", {}) or {}).get("id", "").strip() or None


def _manejar_boton_heridas(telefono: str, button_id: str) -> bool:
    from respuesta_fiable import respuesta_boton_heridas

    texto = respuesta_boton_heridas(button_id)
    if not texto:
        return False
    enviar_mensaje_whatsapp(telefono, texto)
    try:
        from heridas_sheet import registrar_interesado_heridas_async

        estado = {
            "heridas_presencial": "Quiere presencial",
            "heridas_online": "Quiere online",
            "heridas_apartar": "Quiere apartar",
        }.get(button_id, "Botón ficha")
        registrar_interesado_heridas_async(
            telefono=telefono,
            consulta=f"Botón {button_id}",
            fuente="Botón ficha heridas WA",
            estado=estado,
        )
    except Exception as e:
        logger.debug("Hoja heridas botón: %s", e)
    logger.info("Botón heridas '%s' atendido para %s", button_id, telefono)
    return True


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

    button_id = _extraer_id_boton_interactive(mensaje_info)
    if button_id and button_id.startswith("heridas_") and _manejar_boton_heridas(
        numero_remitente, button_id
    ):
        return None

    # Botón interactivo genérico → tratarlo como texto del paciente
    if tipo_mensaje == "interactive" and texto_boton:
        mensaje_info = {
            **mensaje_info,
            "type": "text",
            "text": {"body": texto_boton},
        }
        tipo_mensaje = "text"

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
            # Sync hoja heridas / analytics solo en Modo Pro — en hilo aparte
            try:
                from heridas_sheet import (
                    es_pedido_sync_panel_heridas,
                    es_pregunta_estado_sync_heridas,
                    intentar_comando_sync_heridas,
                    marcar_sync_heridas_pendiente,
                    responder_estado_sync_heridas,
                )
                from analytics import (
                    es_pedido_sync_panel_analytics,
                    intentar_comando_sync_analytics,
                )

                storage.renovar_sesion_equipo(
                    numero_remitente, config.EQUIPO_SESION_HORAS
                )

                if es_pregunta_estado_sync_heridas(texto_paciente):
                    estado = responder_estado_sync_heridas(numero_remitente)
                    if estado:
                        enviar_mensaje_whatsapp(numero_remitente, estado)
                        return None

                if es_pedido_sync_panel_heridas(texto_paciente):
                    import threading

                    tel = numero_remitente
                    marcar_sync_heridas_pendiente(tel)
                    enviar_mensaje_whatsapp(
                        tel,
                        "Actualizo la hoja de heridas ahora… te confirmo en unos segundos ✨",
                    )

                    def _sync_bg():
                        done = threading.Event()

                        def _run():
                            try:
                                sync_msg = intentar_comando_sync_heridas(
                                    tel,
                                    "sincroniza la hoja de heridas",
                                    requerir_modo_pro=False,
                                )
                                if sync_msg:
                                    enviar_mensaje_whatsapp(tel, sync_msg)
                                else:
                                    enviar_mensaje_whatsapp(
                                        tel,
                                        "No pude completar el sync. Revisa que estés en *Modo Pro* "
                                        "y vuelve a escribir *sincroniza la hoja de heridas*.",
                                    )
                            except Exception as err:
                                logger.exception("Sync heridas bg: %s", err)
                                try:
                                    from heridas_sheet import limpiar_sync_heridas_pendiente

                                    limpiar_sync_heridas_pendiente(tel)
                                except Exception:
                                    pass
                                try:
                                    enviar_mensaje_whatsapp(
                                        tel,
                                        f"No pude sincronizar la hoja ({type(err).__name__}: {err}). "
                                        "WhatsApp sigue activo; reintenta en un minuto.",
                                    )
                                except Exception:
                                    pass
                            finally:
                                done.set()

                        threading.Thread(target=_run, daemon=True).start()
                        if not done.wait(timeout=90):
                            try:
                                enviar_mensaje_whatsapp(
                                    tel,
                                    "El sync va lento (Sheets). Los datos pueden seguir "
                                    "escribiéndose; te confirmo aquí cuando termine "
                                    "(o pregunta *ya quedó?*).",
                                )
                            except Exception:
                                pass

                    threading.Thread(target=_sync_bg, daemon=True).start()
                    logger.info("Sync heridas (Modo Pro, async) %s", tel[-4:])
                    return None

                if es_pedido_sync_panel_analytics(texto_paciente):
                    import threading

                    tel = numero_remitente
                    enviar_mensaje_whatsapp(
                        tel,
                        "Actualizo la hoja de *Analytics* ahora… te confirmo en unos segundos ✨",
                    )

                    def _sync_analytics_bg():
                        done = threading.Event()

                        def _run():
                            try:
                                sync_msg = intentar_comando_sync_analytics(
                                    tel,
                                    "sincroniza la hoja de analytics",
                                    requerir_modo_pro=False,
                                )
                                if sync_msg:
                                    enviar_mensaje_whatsapp(tel, sync_msg)
                                else:
                                    enviar_mensaje_whatsapp(
                                        tel,
                                        "No pude completar Analytics. Revisa *Modo Pro* y reintenta "
                                        "*sincroniza la hoja de analytics*.",
                                    )
                            except Exception as err:
                                logger.exception("Sync analytics bg: %s", err)
                                try:
                                    enviar_mensaje_whatsapp(
                                        tel,
                                        f"No pude sincronizar Analytics ({type(err).__name__}: {err}). "
                                        "Reintenta en un minuto.",
                                    )
                                except Exception:
                                    pass
                            finally:
                                done.set()

                        threading.Thread(target=_run, daemon=True).start()
                        if not done.wait(timeout=90):
                            try:
                                enviar_mensaje_whatsapp(
                                    tel,
                                    "Analytics va lento (Sheets); te confirmo cuando termine.",
                                )
                            except Exception:
                                pass

                    threading.Thread(target=_sync_analytics_bg, daemon=True).start()
                    logger.info("Sync analytics (Modo Pro, async) %s", tel[-4:])
                    return None
            except Exception as e:
                logger.warning("Comando sync Modo Pro: %s", e)
            return texto_paciente

        # Si preguntan por un sync reciente sin sesión Pro, no reintroducir como paciente
        try:
            from heridas_sheet import (
                es_pregunta_estado_sync_heridas,
                responder_estado_sync_heridas,
            )

            if es_pregunta_estado_sync_heridas(texto_paciente):
                estado = responder_estado_sync_heridas(numero_remitente)
                if estado:
                    enviar_mensaje_whatsapp(numero_remitente, estado)
                    return None
        except Exception:
            pass

        # Personal Inpulso sin Modo Pro: no tratar como paciente nuevo con saludo de recepción
        miembro = config.identificar_miembro_equipo(numero_remitente)
        if miembro and len(texto_paciente.strip()) < 80:
            baja = texto_paciente.strip().lower()
            if baja in (
                "muchas gracias",
                "muchas gracias!",
                "gracias",
                "gracias!",
                "ok",
                "listo",
                "perfecto",
            ) or baja.startswith("gracias"):
                enviar_mensaje_whatsapp(
                    numero_remitente,
                    f"De nada, {miembro} 😊\n"
                    "Si necesitas *Modo Pro* otra vez, escribe *MODO PRO*.",
                )
                return None

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
                    "NO pidas nombre para charlar; solo al agendar o inscribirse."
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
                "Interés inscripción taller heridas",
            )
            enviar_mensaje_whatsapp(
                numero_remitente,
                "¡Perfecto! Te anoté para el taller *Sanando tus heridas del pasado* ✨\n\n"
                "Hay *inscripciones abiertas* (presencial 6 sep / online desde 8 sep). "
                "Dime si te interesa *presencial* u *online* y te oriento con precios "
                "y cómo apartar tu lugar.",
            )
            try:
                from heridas_sheet import registrar_interesado_heridas_async

                registrar_interesado_heridas_async(
                    telefono=numero_remitente,
                    nombre=nombre,
                    consulta="HISTORIA — interés inscripción",
                    fuente="Comando HISTORIA",
                    estado="Interesado",
                )
            except Exception as e:
                logger.warning("Hoja heridas HISTORIA: %s", e)
            logger.info("Interés HISTORIA taller heridas: %s", numero_remitente)
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
                meta_doc = mensaje_info.get(tipo_clave, {}) or {}
                filename = (meta_doc.get("filename") or "").strip()
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
                if tipo_mensaje == "document":
                    from conocimiento import es_mime_pdf, guardar_conocimiento_desde_pdf

                    if es_mime_pdf(mime_type, filename):
                        guardado = guardar_conocimiento_desde_pdf(
                            file_bytes,
                            filename=filename,
                            caption=caption,
                            quien=f"equipo:{miembro_equipo}",
                            sync_sheets=True,
                        )
                        if guardado.get("ok"):
                            texto_descriptivo += (
                                f"\n\n[Sistema: PDF guardado automáticamente en la base "
                                f"para pacientes — conocimiento #{guardado.get('id')} "
                                f"*{(guardado.get('tema') or '')}* "
                                f"({guardado.get('chars', 0)} caracteres). "
                                "Confirma al equipo con un resumen breve de lo guardado. "
                                "NO digas que 'vas a guardarlo': YA está guardado. "
                                "Los pacientes lo usarán vía buscar_conocimiento_clinica.]\n\n"
                                "--- TEXTO EXTRAÍDO DEL PDF ---\n"
                                f"{(guardado.get('texto') or '')[:12000]}"
                            )
                        else:
                            texto_descriptivo += (
                                "\n\n[Sistema: Intenté guardar el PDF en conocimiento pero "
                                f"falló: {guardado.get('mensaje', 'ilegible')}. "
                                "Analiza el archivo; si puedes leerlo, llama "
                                "*guardar_conocimiento_pacientes* con el contenido completo.]"
                            )
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

