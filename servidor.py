import datetime
import logging
import sys
import threading

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request
from google.genai import types

import config
import storage
from chat import procesar_mensaje_ia, reiniciar_chat_paciente
from tools import envolver_mensaje_con_contexto_paciente
from jobs import (
    alertas_citas_background,
    limpiar_inscripciones_pendientes_background,
    verificar_lista_espera_background,
)
from whatsapp import descargar_media_whatsapp, enviar_mensaje_whatsapp, verificar_firma_webhook

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
    scheduler = BackgroundScheduler(timezone=config.ZONA_MEXICO)
    scheduler.add_job(alertas_citas_background, "interval", minutes=15)
    scheduler.add_job(verificar_lista_espera_background, "interval", minutes=15)
    scheduler.add_job(limpiar_inscripciones_pendientes_background, "interval", minutes=60)
    scheduler.start()
    _scheduler_iniciado = True
    logger.info("Scheduler de tareas en segundo plano iniciado")


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "service": "alessia"}, 200


@app.route("/health/config", methods=["GET"])
def health_config():
    """Muestra que variables tiene el servidor (sin revelar valores)."""
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
    }
    faltantes = [k for k, v in checks.items() if k != "FLASK_ENV" and not v]
    return {
        "checks": checks,
        "listo_para_whatsapp": len(faltantes) == 0,
        "faltantes": faltantes,
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
        contenido_con_citas = envolver_mensaje_con_contexto_paciente(
            numero_remitente, contenido_para_ia
        )
        threading.Thread(
            target=procesar_mensaje_ia,
            args=(numero_remitente, contenido_con_citas),
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
            enviar_mensaje_whatsapp(
                numero_remitente,
                "Entendido 😊 He notificado al equipo de recepción. "
                "Una persona te contactará pronto por este mismo chat.",
            )
            logger.info("Escalación humana solicitada por %s", numero_remitente)
            return None

        texto_lower = texto_paciente.lower()
        if any(palabra in texto_lower for palabra in config.PALABRAS_PRIVACIDAD):
            enviar_mensaje_whatsapp(numero_remitente, config.AVISO_PRIVACIDAD)
            return None

        return texto_contexto + texto_paciente

    if tipo_mensaje == "location":
        lat = mensaje_info["location"]["latitude"]
        lng = mensaje_info["location"]["longitude"]
        storage.guardar_ubicacion(numero_remitente, lat, lng)
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
            texto_descriptivo = f"Archivo tipo {tipo_mensaje}."
            if caption:
                texto_descriptivo += f" Texto: {caption}"
            return [
                types.Part(inline_data=types.Blob(data=file_bytes, mime_type=mime_type)),
                types.Part(
                    text=(
                        texto_contexto
                        + texto_descriptivo
                        + f" [COMPROBANTE DE PAGO — teléfono paciente: {numero_remitente}]. "
                        "Analiza si es transferencia COMPLETADA a BANORTE CLABE 072320003548248000 "
                        "o BANAMEX CLABE 002320700928855166. Si es válido, usa confirmar_pago_comprobante "
                        f"con teléfono {numero_remitente}. Si no es legible o inválido, pide otro comprobante."
                    )
                ),
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
