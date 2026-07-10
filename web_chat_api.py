"""Rutas HTTP del chat web — no modifica el webhook de WhatsApp."""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

import config
import storage
from web_chat import (
    hash_ip,
    nueva_sesion_web,
    procesar_mensaje_web,
    sesion_valida,
)

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static" / "web-chat"
bp = Blueprint("web_chat", __name__)


def _origen_permitido() -> bool:
    if not config.IS_PRODUCTION:
        return True
    origin = (request.headers.get("Origin") or "").rstrip("/")
    referer = (request.headers.get("Referer") or "").rstrip("/")
    if origin and origin in config.WEB_CHAT_ORIGINS:
        return True
    if referer:
        for allowed in config.WEB_CHAT_ORIGINS:
            if referer.startswith(allowed):
                return True
    return not origin and not referer


def _cors_headers(response):
    if isinstance(response, tuple):
        resp = response[0]
        extra = response[1:]
    else:
        resp = response
        extra = ()
    origin = request.headers.get("Origin", "")
    if origin.rstrip("/") in config.WEB_CHAT_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
    elif not config.IS_PRODUCTION:
        resp.headers["Access-Control-Allow-Origin"] = origin or "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Vary"] = "Origin"
    return (resp, *extra) if extra else resp


def _deshabilitado():
    return jsonify({"error": "Chat web no disponible"}), 404


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _rate_limit_ok() -> bool:
    return storage.registrar_hit_web_chat(hash_ip(_client_ip()), config.WEB_CHAT_RATE_LIMIT)


@bp.route("/api/web-chat/config", methods=["GET", "OPTIONS"])
def web_chat_config():
    if request.method == "OPTIONS":
        return _cors_headers(jsonify({}))
    if not config.ENABLE_WEB_CHAT:
        return _cors_headers(_deshabilitado())
    return _cors_headers(
        jsonify(
            {
                "enabled": True,
                "whatsapp_url": config.WHATSAPP_PACIENTES_URL,
                "clinica_url": config.CLINICA_WEB_URL,
                "aviso_privacidad_url": config.AVISO_PRIVACIDAD_URL,
            }
        )
    )


@bp.route("/api/web-chat/session", methods=["POST", "OPTIONS"])
def web_chat_session():
    if request.method == "OPTIONS":
        return _cors_headers(jsonify({}))
    if not config.ENABLE_WEB_CHAT:
        return _cors_headers(_deshabilitado())
    if not _origen_permitido():
        return _cors_headers(jsonify({"error": "Origen no permitido"})), 403
    if not _rate_limit_ok():
        return _cors_headers(jsonify({"error": "Demasiadas solicitudes"})), 429
    session_id = nueva_sesion_web()
    return _cors_headers(jsonify({"session_id": session_id}))


@bp.route("/api/web-chat/message", methods=["POST", "OPTIONS"])
def web_chat_message():
    if request.method == "OPTIONS":
        return _cors_headers(jsonify({}))
    if not config.ENABLE_WEB_CHAT:
        return _cors_headers(_deshabilitado())
    if not _origen_permitido():
        return _cors_headers(jsonify({"error": "Origen no permitido"})), 403
    if not _rate_limit_ok():
        return _cors_headers(jsonify({"error": "Demasiadas solicitudes"})), 429

    imagen_bytes = None
    mime_type = "image/jpeg"

    if request.content_type and "multipart/form-data" in request.content_type:
        session_id = (request.form.get("session_id") or "").strip()
        mensaje = (request.form.get("message") or "").strip()
        archivo = request.files.get("image") or request.files.get("file")
        if archivo and archivo.filename:
            imagen_bytes = archivo.read()
            mime_type = archivo.mimetype or "image/jpeg"
            if len(imagen_bytes) > 8 * 1024 * 1024:
                return _cors_headers(jsonify({"error": "Imagen demasiado grande (máx 8MB)"})), 400
    else:
        data = request.get_json(silent=True) or {}
        session_id = (data.get("session_id") or "").strip()
        mensaje = (data.get("message") or "").strip()

    if not sesion_valida(session_id):
        return _cors_headers(jsonify({"error": "Sesión inválida"})), 400
    if not storage.obtener_sesion_web(session_id):
        return _cors_headers(jsonify({"error": "Sesión expirada"})), 404
    if not mensaje and not imagen_bytes:
        return _cors_headers(jsonify({"error": "Mensaje vacío"})), 400

    try:
        reply = procesar_mensaje_web(
            session_id,
            mensaje,
            imagen_bytes=imagen_bytes,
            mime_type=mime_type,
        )
    except ValueError as e:
        return _cors_headers(jsonify({"error": str(e)})), 400
    except Exception as e:
        logger.exception("Error chat web: %s", e)
        return _cors_headers(jsonify({"error": "Error interno"})), 500

    return _cors_headers(jsonify({"session_id": session_id, "reply": reply}))


@bp.route("/static/web-chat/<path:filename>", methods=["GET"])
def web_chat_static(filename: str):
    if not STATIC_DIR.is_dir():
        return "Not found", 404
    return send_from_directory(STATIC_DIR, filename)


def registrar_rutas_web_chat(app):
    app.register_blueprint(bp)
    logger.info(
        "Chat web: %s (orígenes: %s)",
        "activado" if config.ENABLE_WEB_CHAT else "desactivado",
        ", ".join(config.WEB_CHAT_ORIGINS) or "ninguno",
    )
