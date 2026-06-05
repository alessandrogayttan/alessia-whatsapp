import datetime
import logging
import re
import sys
import threading

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request
from google.genai import types

import config
import storage
from bienestar import comando_biblioteca, micro_ejercicio_para_texto
from chat import procesar_mensaje_ia, reiniciar_chat_paciente
from experiencia import calcular_minutos_ruta, guardar_nota_ritual_cierre, guardar_prep_sesion
from tools import (
    envolver_mensaje_con_contexto_paciente,
    notificar_emergencia_paciente,
    notificar_llegada_paciente,
    registrar_escalacion_humana,
)
from jobs import (
    alertas_citas_background,
    dashboard_background,
    frase_del_dia_background,
    limpiar_inscripciones_pendientes_background,
    reporte_semanal_background,
    seguimiento_post_cita_background,
    trivia_semanal_background,
    verificar_lista_espera_background,
    experiencia_diaria_background,
)
from whatsapp import (
    descargar_media_whatsapp,
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
    scheduler.add_job(limpiar_inscripciones_pendientes_background, "interval", minutes=60)
    scheduler.add_job(frase_del_dia_background, "interval", minutes=15)
    scheduler.add_job(trivia_semanal_background, "interval", minutes=15)
    scheduler.add_job(reporte_semanal_background, "interval", minutes=15)
    scheduler.add_job(dashboard_background, "interval", hours=6)
    scheduler.add_job(experiencia_diaria_background, "interval", minutes=15)
    scheduler.start()
    _scheduler_iniciado = True
    logger.info("Scheduler de tareas en segundo plano iniciado")


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
        "advertencias": config.advertencias_lanzamiento(),
    }
    return payload, 200 if listo else 503


@app.route("/health/config", methods=["GET"])
def health_config():
    """Muestra qué variables tiene el servidor (sin revelar valores)."""
    if config.IS_PRODUCTION and config.HEALTH_CONFIG_SECRET:
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

    datos = request.get_json(silent=True)
    if not datos:
        return "OK", 200

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
        contenido_con_citas = envolver_mensaje_con_contexto_paciente(
            numero_remitente, contenido_para_ia
        )
        threading.Thread(
            target=procesar_mensaje_ia,
            args=(numero_remitente, contenido_con_citas),
            daemon=True,
        ).start()

    return "OK", 200


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
            return (
                texto_contexto
                + f"[Sistema: PRIMERA VEZ — Primer contacto por WhatsApp. "
                f"Saluda con '{saludo_hora}', preséntate solo como 'Alessia, de Inpulso 43'. "
                f"Habla como persona real del equipo (recepción). "
                f"PROHIBIDO decir virtual, IA, bot o automatizado. "
                f"Si el mensaje ya incluye una pregunta (taller, cita, precios), respóndela en el mismo mensaje. "
                f"Si no dio su nombre, pregúntalo al final con naturalidad. "
                f"No envíes bloque largo de bienvenida con dirección/estacionamiento salvo que lo pidan.]\n"
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
            storage.eliminar_datos_paciente(numero_remitente)
            reiniciar_chat_paciente(numero_remitente)
            enviar_mensaje_whatsapp(
                numero_remitente,
                "Tus datos locales han sido eliminados de nuestro sistema. "
                "Si tienes citas activas en calendario, contacta a recepción para cancelarlas.",
            )
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
    config.validar_config_minima()
    config.validar_config_produccion()
    storage.init_db()
    _iniciar_scheduler()
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
