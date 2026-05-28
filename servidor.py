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
from chat import procesar_mensaje_ia
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


def _iniciar_scheduler():
    scheduler = BackgroundScheduler(timezone=config.ZONA_MEXICO)
    scheduler.add_job(alertas_citas_background, "interval", minutes=15)
    scheduler.add_job(verificar_lista_espera_background, "interval", minutes=15)
    scheduler.add_job(limpiar_inscripciones_pendientes_background, "interval", minutes=60)
    scheduler.start()
    logger.info("Scheduler de tareas en segundo plano iniciado")


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "service": "alessia"}, 200


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

    try:
        mensaje_info = datos["entry"][0]["changes"][0]["value"]["messages"][0]
        mensaje_id = mensaje_info["id"]

        if storage.mensaje_ya_procesado(mensaje_id):
            return "OK", 200
        storage.marcar_mensaje_procesado(mensaje_id)

        numero_remitente = mensaje_info["from"]
        tipo_mensaje = mensaje_info.get("type")

        zona_mexico = pytz.timezone(config.ZONA_MEXICO)
        hora_exacta = datetime.datetime.now(zona_mexico).strftime("%Y-%m-%d %H:%M")
        texto_contexto = f"[Sistema: Mensaje recibido el {hora_exacta}] "
        contenido_para_ia = None

        if tipo_mensaje == "text":
            texto_paciente = mensaje_info["text"]["body"].strip()

            if texto_paciente.upper() == "ELIMINAR DATOS":
                storage.eliminar_datos_paciente(numero_remitente)
                enviar_mensaje_whatsapp(
                    numero_remitente,
                    "Tus datos locales han sido eliminados de nuestro sistema. "
                    "Si tienes citas activas en calendario, contacta a recepción para cancelarlas.",
                )
                return "OK", 200

            if texto_paciente.upper() == "HABLAR CON PERSONA":
                enviar_mensaje_whatsapp(
                    numero_remitente,
                    "Entendido 😊 He notificado al equipo de recepción. "
                    "Una persona te contactará pronto por este mismo chat.",
                )
                logger.info("Escalación humana solicitada por %s", numero_remitente)
                return "OK", 200

            contenido_para_ia = texto_contexto + texto_paciente

        elif tipo_mensaje == "location":
            lat = mensaje_info["location"]["latitude"]
            lng = mensaje_info["location"]["longitude"]
            storage.guardar_ubicacion(numero_remitente, lat, lng)
            contenido_para_ia = (
                texto_contexto
                + f"[El paciente envió su ubicación {lat},{lng}]. "
                "Usa obtener_ruta_inpulso y responde el tiempo."
            )

        elif tipo_mensaje in ["image", "video", "audio", "voice", "document"]:
            tipo_clave = "voice" if tipo_mensaje == "voice" else tipo_mensaje
            media_id = mensaje_info[tipo_clave]["id"]
            file_bytes, mime_type = descargar_media_whatsapp(media_id)

            if file_bytes:
                caption = mensaje_info.get(tipo_clave, {}).get("caption", "")
                texto_descriptivo = f"Archivo tipo {tipo_mensaje}."
                if caption:
                    texto_descriptivo += f" Texto: {caption}"
                contenido_para_ia = [
                    types.Part(
                        inline_data=types.Blob(data=file_bytes, mime_type=mime_type)
                    ),
                    types.Part(
                        text=(
                            texto_contexto
                            + texto_descriptivo
                            + " [Nota: Si parece comprobante de pago, agradece y dile "
                            "que recepción lo verificará pronto. NO confirmes el pago automáticamente]."
                        )
                    ),
                ]
            else:
                contenido_para_ia = texto_contexto + "Error al descargar archivo."
        else:
            return "OK", 200

        if contenido_para_ia:
            es_primer_contacto = not storage.paciente_registrado(numero_remitente)
            threading.Thread(
                target=procesar_mensaje_ia,
                args=(numero_remitente, contenido_para_ia, es_primer_contacto),
                daemon=True,
            ).start()

    except (KeyError, IndexError):
        pass

    return "OK", 200


def create_app():
    config.validar_config_produccion()
    storage.init_db()
    _iniciar_scheduler()
    return app


if __name__ == "__main__":
    create_app()
    logger.info("Alessia escuchando en puerto %s (modo %s)", config.PORT, config.FLASK_ENV)
    app.run(host="0.0.0.0", port=config.PORT, debug=not config.IS_PRODUCTION)
