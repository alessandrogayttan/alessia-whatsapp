import datetime
import logging
import sys
import threading
import time
from collections import defaultdict

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, request

import config
import storage
from chat import procesar_mensaje_ia
from message_queue import encolar_mensaje_texto, procesar_cola
from observability import init_sentry, metricas_fallos
from tools import envolver_mensaje_con_contexto_paciente
from whatsapp import (
    enviar_ack_inmediato,
    marcar_leido_y_escribiendo,
    verificar_firma_webhook,
)
from whatsapp_inbound import (
    _extraer_mensajes_whatsapp,
    _procesar_estados_whatsapp,
    _registrar_consentimiento_si_aplica,
    preparar_contenido_mensaje,
)

# Compat tests / imports antiguos
_preparar_contenido_mensaje = preparar_contenido_mensaje

from jobs import (
    alertas_citas_background,
    backup_db_background,
    dashboard_background,
    frase_del_dia_background,
    limpiar_inscripciones_pendientes_background,
    procesar_cola_background,
    reporte_semanal_background,
    renotificar_escalaciones_background,
    reindexar_rag_inpulso_background,
    seguimiento_post_cita_background,
    sincronizar_catalogo_web_background,
    sincronizar_catalogo_whatsapp_background,
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

from web_chat_api import registrar_rutas_web_chat

registrar_rutas_web_chat(app)

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
_scheduler = None

_JOB_DEFAULTS = {
    "max_instances": 1,
    "coalesce": True,
    "misfire_grace_time": 60,
}


def _add_job(scheduler, func, trigger, **kwargs):
    opts = {**_JOB_DEFAULTS, **kwargs}
    scheduler.add_job(func, trigger, **opts)


def _iniciar_scheduler():
    global _scheduler_iniciado, _scheduler
    if _scheduler_iniciado:
        return
    if not config.ENABLE_SCHEDULER:
        logger.info("Scheduler desactivado (ENABLE_SCHEDULER=0)")
        return
    scheduler = BackgroundScheduler(timezone=config.ZONA_MEXICO)
    _add_job(scheduler, alertas_citas_background, "interval", minutes=15)
    _add_job(scheduler, seguimiento_post_cita_background, "interval", minutes=30)
    _add_job(scheduler, verificar_lista_espera_background, "interval", minutes=15)
    _add_job(scheduler, detectar_nuevos_talleres_background, "interval", minutes=10)
    _add_job(scheduler, limpiar_inscripciones_pendientes_background, "interval", minutes=60)
    _add_job(scheduler, frase_del_dia_background, "interval", minutes=15)
    _add_job(scheduler, trivia_semanal_background, "interval", minutes=15)
    _add_job(scheduler, reporte_semanal_background, "interval", minutes=15)
    _add_job(scheduler, dashboard_background, "interval", hours=6)
    _add_job(scheduler, experiencia_diaria_background, "interval", minutes=15)
    _add_job(scheduler, procesar_cola_background, "interval", seconds=5)
    _add_job(scheduler, calendario_keepalive_background, "interval", minutes=5)
    _add_job(scheduler, renotificar_escalaciones_background, "interval", minutes=5)
    _add_job(scheduler, backup_db_background, "interval", hours=24)
    _add_job(scheduler, sincronizar_catalogo_web_background, "interval", minutes=30)
    _add_job(scheduler, sincronizar_catalogo_whatsapp_background, "interval", minutes=30)
    _add_job(scheduler, sincronizar_web_background, "interval", hours=24)
    _add_job(scheduler, reindexar_rag_inpulso_background, "interval", hours=6)
    scheduler.start()
    _scheduler = scheduler
    _scheduler_iniciado = True
    import atexit

    atexit.register(_detener_scheduler)
    logger.info("Scheduler iniciado (max_instances=1, coalesce=True)")


def _detener_scheduler():
    global _scheduler, _scheduler_iniciado
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")
    except Exception as e:
        logger.debug("Shutdown scheduler: %s", e)
    finally:
        _scheduler = None
        _scheduler_iniciado = False


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
    from seguridad import metrics_requieren_secreto

    if metrics_requieren_secreto(config.IS_PRODUCTION):
        import hmac

        if not config.HEALTH_CONFIG_SECRET:
            return {"error": "Not configured"}, 404
        token = request.args.get("secret") or request.headers.get("X-Health-Secret", "")
        if not hmac.compare_digest(token, config.HEALTH_CONFIG_SECRET):
            return {"error": "Forbidden"}, 403
    base = {
        "cola_pendiente": storage.contar_cola_pendiente(),
        "cola_por_estado": storage.contar_cola_por_estado(),
        "fallos": metricas_fallos(),
        "recepcion_configurada": bool(config.RECEPCION_WHATSAPP),
        "scheduler_activo": _scheduler_iniciado,
        "plantillas_recordatorio": {
            "24h": bool(config.WHATSAPP_TEMPLATE_24H),
            "2h": bool(config.WHATSAPP_TEMPLATE_2H),
            "escalacion": bool(config.WHATSAPP_TEMPLATE_ESCALACION),
        },
    }
    try:
        base.update(storage.resumen_metricas_operativas())
    except Exception as e:
        logger.debug("Métricas extendidas no disponibles: %s", e)
    return base, 200


@app.route("/health/config", methods=["GET"])
def health_config():
    """Muestra qué variables tiene el servidor (sin revelar valores)."""
    if config.IS_PRODUCTION and not config.HEALTH_CONFIG_SECRET:
        return {"error": "Not configured"}, 404
    if config.IS_PRODUCTION:
        import hmac

        token = request.args.get("secret") or request.headers.get("X-Health-Secret", "")
        if not hmac.compare_digest(token, config.HEALTH_CONFIG_SECRET):
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
        "RECEPCION_WHATSAPP": bool(config.RECEPCION_WHATSAPP),
        "WHATSAPP_TEMPLATE_24H": bool(config.WHATSAPP_TEMPLATE_24H),
        "WHATSAPP_TEMPLATE_2H": bool(config.WHATSAPP_TEMPLATE_2H),
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


def create_app():
    init_sentry()
    config.validar_config_minima()
    config.validar_config_produccion()
    storage.init_db()
    from message_queue import recuperar_atascados

    n_stuck = recuperar_atascados(minutos=5)
    if n_stuck:
        logger.warning("Reclamados %s mensajes atascados al arranque", n_stuck)
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
    