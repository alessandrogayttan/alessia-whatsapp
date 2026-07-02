import datetime
import logging
import re
import sys
import threading
import time
from collections import defaultdict

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request
from google.genai import types

import config
import storage
from bienestar import comando_biblioteca, micro_ejercicio_para_texto
from chat import procesar_mensaje_ia, reiniciar_chat_paciente
from experiencia import calcular_minutos_ruta, guardar_nota_ritual_cierre, guardar_prep_sesion
from message_queue import encolar_mensaje_texto, procesar_cola
from observability import init_sentry, metricas_fallos
from tools import (
    eliminar_datos_arco,
    envolver_mensaje_con_contexto_paciente,
    notificar_emergencia_paciente,
    notificar_llegada_paciente,
    registrar_escalacion_humana,
)
from jobs import (
    alertas_citas_background,
    backup_db_background,
    dashboard_background,
    frase_del_dia_background,
    limpiar_inscripciones_pendientes_background,
    procesar_cola_background,
    reporte_semanal_background,
    renotificar_escalaciones_background,
    seguimiento_post_cita_background,
    sincronizar_web_background,
    trivia_semanal_background,
    detectar_nuevos_talleres_background,
    verificar_lista_espera_background,
    experiencia_diaria_background,
    calendario_keepalive_background,
)
from whatsapp import (
    descargar_media_whatsapp,
    enviar_ack_inmediato,
    enviar_mensaje_whatsapp,
    marcar_leido_y_escribiendo,
    verificar_firma_webhook,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_webhook_hits: dict[str, list[float]] = defaultdict(list)


def _rate_limit_ok(ip: str) -> bool:
    ahora = time.time()
    ventana = ahora - 60
    hits = [t for t in _webhook_hits[ip] if t > ventana]
    _webhook_hits[ip] = hits
    if len(hits) >= config.WEBHOOK_RATE_LIMIT:
        return False
    hits.append(ahora)
    return True


_scheduler_iniciado = False


def _iniciar_scheduler():
    global _scheduler_iniciado
    if _scheduler_iniciado:
        return
    if not config.ENABLE_SCHEDULER:
        logger.info("Scheduler desactivado (ENABLE_SCHEDULER=0)")
        return
    scheduler = BackgroundScheduler(timezone=config.ZONA_MEXICO)
    scheduler.add_job(alertas_citas_background, "interval", minutes=15)
    scheduler.add_job(seguimiento_post_cita_background, "interval", minutes=30)
    scheduler.add_job(verificar_lista_espera_background, "interval", minutes=15)
    scheduler.add_job(detectar_nuevos_talleres_background, "interval", minutes=10)
    scheduler.add_job(limpiar_inscripciones_pendientes_background, "interval", minutes=60)
    scheduler.add_job(frase_del_dia_background, "interval", minutes=15)
    scheduler.add_job(trivia_semanal_background, "interval", minutes=15)
    scheduler.add_job(reporte_semanal_background, "interval", minutes=15)
    scheduler.add_job(dashboard_background, "interval", hours=6)
    scheduler.add_job(experiencia_diaria_background, "interval", minutes=15)
    scheduler.add_job(procesar_cola_background, "interval", seconds=5)
    scheduler.add_job(calendario_keepalive_background, "interval", minutes=5)
    scheduler.add_job(renotificar_escalaciones_background, "interval", minutes=5)
    scheduler.add_job(backup_db_background, "interval", hours=24)
    scheduler.add_job(sincronizar_web_background, "interval", hours=24)
    scheduler.start()
    _scheduler_iniciado = True
    logger.info("Scheduler de tareas en segundo plano iniciado")


@app.route("/", methods=["GET"])
def root():
    """Raíz: meta tag para verificación de dominio Meta (si está configurada)."""
    code = config.META_DOMAIN_VERIFICATION_CODE
    if code:
        html = (
            "<!DOCTYPE html><html><head>"
            f'<meta name="facebook-domain-verification" content="{code}" />'
            "</head><body>Alessia — Inpulso 43</body></html>"
        )
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}
    return "Alessia OK", 200


def _meta_domain_verification_response(filename: str):
    code = config.META_DOMAIN_VERIFICATION_CODE
    if not code:
        return "Not configured", 404
    expected = config.META_DOMAIN_VERIFICATION_FILE
    allowed = {expected, "facebook-domain-verification.html", f"{code}.html"}
    if filename not in allowed:
        return "Not found", 404
    body = f"facebook-domain-verification: {code}"
    return body, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/facebook-domain-verification.html", methods=["GET"])
def meta_domain_verification_default():
    return _meta_domain_verification_response("facebook-domain-verification.html")


@app.route("/<verification_file>.html", methods=["GET"])
def meta_domain_verification_named(verification_file: str):
    return _meta_domain_verification_response(f"{verification_file}.html")


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "service": "alessia"}, 200


@app.route("/health/ready", methods=["GET"])
def health_ready():
    """Readiness: falla si faltan piezas críticas para atender WhatsApp."""
    from pathlib import Path

    bloqueantes = []
    if not config.TOKEN_WHATSAPP:
        bloqueantes.append("TOKEN_WHATSAPP")
    if not config.GEMINI_API_KEY:
        bloqueantes.append("GEMINI_API_KEY")
    if not config.ID_TELEFONO:
        bloqueantes.append("ID_TELEFONO")
    google_ok = bool(config.GOOGLE_SERVICE_ACCOUNT_JSON) or Path(
        config.SERVICE_ACCOUNT_FILE
    ).is_file()
    if not google_ok:
        bloqueantes.append("GOOGLE_CREDENTIALS")

    advertencias = config.advertencias_lanzamiento()
    # Calendario: no bloquear /health/ready (evita 504 en DO); se verifica en keepalive
    from tools import estado_calendarios_cache

    advertencias.extend(estado_calendarios_cache())

    db_ok = True
    try:
        Path(config.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
        storage.init_db()
        if not storage.ping_db():
            raise RuntimeError("ping falló")
    except Exception as e:
        db_ok = False
        bloqueantes.append(f"DATABASE ({e})")

    listo = not bloqueantes and db_ok
    payload = {
        "ready": listo,
        "scheduler": config.ENABLE_SCHEDULER and _scheduler_iniciado,
        "bloqueantes": bloqueantes,
        "advertencias": advertencias,
    }
    return payload, 200 if listo else 503


@app.route("/health/metrics", methods=["GET"])
def health_metrics():
    """Métricas operativas básicas (sin PII)."""
    if config.IS_PRODUCTION and config.HEALTH_CONFIG_SECRET:
        token = request.args.get("secret") or request.headers.get("X-Health-Secret", "")
        if token != config.HEALTH_CONFIG_SECRET:
            return {"error": "Forbidden"}, 403
    return {
        "cola_pendiente": storage.contar_cola_pendiente(),
        "fallos": metricas_fallos(),
    }, 200


@app.route("/health/config", methods=["GET"])
def health_config():
    """Muestra qué variables tiene el servidor (sin revelar valores)."""
    if config.IS_PRODUCTION and not config.HEALTH_CONFIG_SECRET:
        return {"error": "Not configured"}, 404
    if config.IS_PRODUCTION:
        token = request.args.get("secret") or request.headers.get("X-Health-Secret", "")
        if token != config.HEALTH_CONFIG_SECRET:
            return {"error": "Forbidden"}, 403

    from pathlib import Path
    google_ok = bool(config.GOOGLE_SERVICE_ACCOUNT_JSON) or Path(
        config.SERVICE_ACCOUNT_FILE
    ).is_file()
    checks = {
        "TOKEN_WHATSAPP": bool(config.TOKEN_WHATSAPP),
        "ID_TELEFONO": bool(config.ID_TELEFONO),
        "WHATSAPP_VERIFY_TOKEN": bool(config.WHATSAPP_VERIFY_TOKEN),
        "WHATSAPP_APP_SECRET": bool(config.WHATSAPP_APP_SECRET),
        "GEMINI_API_KEY": bool(config.GEMINI_API_KEY),
        "ID_HOJA_CALCULO": bool(config.ID_HOJA_CALCULO),
        "GOOGLE_CREDENTIALS": google_ok,
        "FLASK_ENV": config.FLASK_ENV,
        "ENABLE_SCHEDULER": config.ENABLE_SCHEDULER,
        "ENABLE_LAUNCH_ACK": config.ENABLE_LAUNCH_ACK,
    }
    faltantes = [k for k, v in checks.items() if k != "FLASK_ENV" and not v]
    return {
        "checks": checks,
        "listo_para_whatsapp": len(faltantes) == 0,
        "faltantes": faltantes,
        "advertencias": config.advertencias_lanzamiento(),
    }, 200


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if token != config.WHATSAPP_VERIFY_TOKEN:
            logger.warning("Intento de verificación con token inválido")
            return "Forbidden", 403
        return challenge or "OK"

    raw_body = request.get_data()
    firma = request.headers.get("X-Hub-Signature-256")
    if not verificar_firma_webhook(raw_body, firma):
        logger.warning("Webhook POST con firma inválida")
        return "Forbidden", 403

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    client_ip = client_ip.split(",")[0].strip()
    if not _rate_limit_ok(client_ip):
        logger.warning("Rate limit webhook excedido: %s", client_ip)
        return "Too Many Requests", 429

    datos = request.get_json(silent=True)
    if not datos:
        return "OK", 200

    _procesar_estados_whatsapp(datos)

    for mensaje_info in _extraer_mensajes_whatsapp(datos):
        mensaje_id = mensaje_info.get("id")
        if not mensaje_id:
            continue
        if not storage.reservar_mensaje_para_procesar(mensaje_id):
            logger.info("Mensaje duplicado ignorado: %s", mensaje_id)
            continue

        contenido_para_ia = _preparar_contenido_mensaje(mensaje_info)
        if contenido_para_ia is None:
            continue

        numero_remitente = mensaje_info["from"]
        marcar_leido_y_escribiendo(mensaje_id)
        enviar_ack_inmediato(numero_remitente)
        _registrar_consentimiento_si_aplica(numero_remitente)
        contenido_con_citas = envolver_mensaje_con_contexto_paciente(
            numero_remitente, contenido_para_ia
        )
        if isinstance(contenido_con_citas, str):
            encolar_mensaje_texto(numero_remitente, contenido_con_citas)
        else:
            threading.Thread(
                target=procesar_mensaje_ia,
                args=(numero_remitente, contenido_con_citas),
                daemon=True,
            ).start()

    return "OK", 200


def _registrar_consentimiento_si_aplica(numero: str):
    if config.identificar_terapeuta(numero):
        return
    if storage.necesita_consentimiento(numero):
        storage.registrar_consentimiento(numero)


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


def _preparar_contenido_mensaje(mensaje_info: dict):
    numero_remitente = mensaje_info["from"]
    tipo_mensaje = mensaje_info.get("type")

    zona_mexico = pytz.timezone(config.ZONA_MEXICO)
    hora_exacta = datetime.datetime.now(zona_mexico).strftime("%Y-%m-%d %H:%M")
    texto_contexto = f"[Sistema: Mensaje recibido el {hora_exacta}] "

    if tipo_mensaje == "text":
        texto_paciente = mensaje_info["text"]["body"].strip()
        es_terapeuta = config.identificar_terapeuta(numero_remitente)

        if es_terapeuta:
            return texto_contexto + f"[Modo staff: {es_terapeuta}]\n" + texto_paciente

        nombre_detectado = _extraer_nombre_del_mensaje(texto_paciente)
        if nombre_detectado:
            storage.guardar_nombre_casual(numero_remitente, nombre_detectado)

        if storage.es_primera_vez(numero_remitente):
            storage.marcar_no_primera_vez(numero_remitente)
            storage.obtener_o_crear_codigo_referido(numero_remitente)
            enviar_mensaje_whatsapp(numero_remitente, config.AVISO_PRIVACIDAD)
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
                f"Si el mensaje incluye una pregunta, respóndela en el mismo mensaje con cariño. "
                f"El aviso de privacidad ya fue enviado automáticamente.]\n"
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
                storage.guardar_checkin_emocional(numero_remitente, escala)
                return (
                    texto_contexto
                    + f"[Sistema: Check-in emocional registrado ({escala}/10). "
                    f"Agradece con calidez; si es bajo (1-4), ofrece apoyo sin alarmar.]\n"
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

        if texto_paciente.upper() == "HABLAR CON PERSONA":
            registrar_escalacion_humana(numero_remitente)
            enviar_mensaje_whatsapp(
                numero_remitente,
                "Entendido 😊 He notificado al equipo de recepción. "
                "Una persona te contactará pronto por este mismo chat.",
            )
            logger.info("Escalación humana solicitada por %s", numero_remitente)
            return None

        if any(palabra in texto_lower for palabra in config.PALABRAS_PRIVACIDAD):
            enviar_mensaje_whatsapp(numero_remitente, config.AVISO_PRIVACIDAD)
            return None

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

        return texto_contexto + texto_paciente

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
                instruccion_pago = (
                    f" [COMPROBANTE DE PAGO — teléfono paciente: {numero_remitente}]. "
                    "Analiza internamente: monto numérico, cuenta destino, estatus COMPLETADO. "
                    "Cuentas válidas: BANORTE CLABE 072320003548248000 o "
                    "BANAMEX CLABE 002320700928855166. "
                    "OBLIGATORIO: llama confirmar_pago_comprobante con el monto. "
                    "Al paciente NO le digas que hay confirmación automática por IA."
                )
            return [
                types.Part(inline_data=types.Blob(data=file_bytes, mime_type=mime_type)),
                types.Part(text=(texto_contexto + texto_descriptivo + instruccion_pago)),
            ]
        return texto_contexto + "Error al descargar archivo."

    return None


def create_app():
    init_sentry()
    config.validar_config_minima()
    config.validar_config_produccion()
    storage.init_db()
    _iniciar_scheduler()
    procesados = procesar_cola(max_items=20)
    if procesados:
        logger.info("Cola recuperada al arranque: %s mensajes", procesados)
    from google_client import email_cuenta_servicio, verificar_credenciales_google
    from tools import verificar_acceso_calendarios

    try:
        verificar_credenciales_google()
        cal_fallos = verificar_acceso_calendarios(rapido=True)
        if cal_fallos:
            logger.error(
                "CALENDARIO NO ACCESIBLE al arranque: %s. Cuenta servicio: %s",
                "; ".join(cal_fallos),
                email_cuenta_servicio() or "desconocida",
            )
        else:
            logger.info("Calendarios Google OK (%s)", ", ".join(config.CALENDARIOS_CRITICOS))
    except Exception as e:
        logger.error("Google Calendar no disponible al arranque: %s", e)
    logger.info(
        "Alessia lista — WhatsApp:%s Gemini:%s VerifyToken:%s AppSecret:%s GoogleJSON:%s",
        "OK" if config.TOKEN_WHATSAPP else "FALTA",
        "OK" if config.GEMINI_API_KEY else "FALTA",
        "OK" if config.WHATSAPP_VERIFY_TOKEN else "FALTA",
        "OK" if config.WHATSAPP_APP_SECRET else "FALTA",
        "OK" if config.GOOGLE_SERVICE_ACCOUNT_JSON or __import__("pathlib").Path(config.SERVICE_ACCOUNT_FILE).is_file() else "FALTA",
    )
    return app


if __name__ == "__main__":
    create_app()
    logger.info("Alessia escuchando en puerto %s (modo %s)", config.PORT, config.FLASK_ENV)
    app.run(host="0.0.0.0", port=config.PORT, debug=not config.IS_PRODUCTION)
