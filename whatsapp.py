import hashlib
import hmac
import json
import logging
import time

import requests

import config

logger = logging.getLogger(__name__)


def verificar_firma_webhook(payload: bytes, signature_header: str | None) -> bool:
    if not config.WHATSAPP_APP_SECRET:
        logger.warning(
            "WHATSAPP_APP_SECRET no configurado: se omite verificación de firma. "
            "Agrégalo desde Meta Developers > Configuración > Básica."
        )
        return True
    if not signature_header:
        return False
    expected = hmac.new(
        config.WHATSAPP_APP_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


def normalizar_telefono(telefono: str) -> str:
    if telefono.startswith("521") and len(telefono) == 13:
        return telefono.replace("521", "52", 1)
    return telefono


def _partir_mensaje(texto: str, max_len: int | None = None) -> list[str]:
    """Divide mensajes largos respetando el límite de WhatsApp (~4096 chars)."""
    limite = max_len or config.WHATSAPP_MAX_CHARS
    if len(texto) <= limite:
        return [texto]

    partes = []
    restante = texto
    while restante:
        if len(restante) <= limite:
            partes.append(restante)
            break
        corte = restante.rfind("\n", 0, limite)
        if corte < limite // 2:
            corte = restante.rfind(" ", 0, limite)
        if corte < limite // 2:
            corte = limite
        partes.append(restante[:corte].rstrip())
        restante = restante[corte:].lstrip()

    return partes


def _enviar_payload(telefono_destino: str, payload: dict) -> bool:
    telefono_destino = normalizar_telefono(telefono_destino)
    url = f"https://graph.facebook.com/v19.0/{config.ID_TELEFONO}/messages"
    headers = {
        "Authorization": f"Bearer {config.TOKEN_WHATSAPP}",
        "Content-Type": "application/json",
    }
    payload = {**payload, "messaging_product": "whatsapp", "to": telefono_destino}
    try:
        res = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
        if res.status_code != 200:
            logger.error("WhatsApp API error %s: %s", res.status_code, res.text)
            return False
        return True
    except requests.RequestException as e:
        logger.error("Error enviando mensaje WhatsApp: %s", e)
        return False


def marcar_leido_y_escribiendo(message_id: str) -> bool:
    """Muestra indicador 'escribiendo…' mientras la IA procesa."""
    if not message_id or not config.ID_TELEFONO:
        return False
    url = f"https://graph.facebook.com/v19.0/{config.ID_TELEFONO}/messages"
    headers = {
        "Authorization": f"Bearer {config.TOKEN_WHATSAPP}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }
    try:
        res = requests.post(url, headers=headers, data=json.dumps(data), timeout=15)
        return res.status_code == 200
    except requests.RequestException as e:
        logger.debug("Typing indicator no disponible: %s", e)
        return False


def enviar_mensaje_whatsapp(telefono_destino: str, texto: str) -> bool:
    partes = _partir_mensaje(texto)
    ok = True
    for i, parte in enumerate(partes):
        if i > 0:
            time.sleep(0.3)
        if not _enviar_payload(
            telefono_destino,
            {"type": "text", "text": {"body": parte}},
        ):
            ok = False
    return ok


def enviar_plantilla_whatsapp(
    telefono_destino: str,
    nombre_plantilla: str,
    parametros: list[str] | None = None,
    idioma: str | None = None,
) -> bool:
    """Envía plantilla preaprobada de Meta (fuera de ventana 24 h)."""
    if not nombre_plantilla:
        return False

    template = {
        "name": nombre_plantilla,
        "language": {"code": idioma or config.WHATSAPP_TEMPLATE_LANG},
    }
    if parametros:
        template["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": str(p)} for p in parametros],
            }
        ]

    return _enviar_payload(telefono_destino, {"type": "template", "template": template})


def enviar_recordatorio(
    telefono: str,
    texto_libre: str,
    nombre_plantilla: str = "",
    parametros_plantilla: list[str] | None = None,
) -> bool:
    """
    Intenta plantilla Meta si está configurada; si falla, usa texto libre.
    """
    if nombre_plantilla:
        if enviar_plantilla_whatsapp(telefono, nombre_plantilla, parametros_plantilla):
            return True
        logger.warning(
            "Plantilla '%s' falló para %s; intentando texto libre.",
            nombre_plantilla,
            telefono,
        )
    return enviar_mensaje_whatsapp(telefono, texto_libre)


def descargar_media_whatsapp(media_id: str):
    url_info = f"https://graph.facebook.com/v19.0/{media_id}"
    headers = {"Authorization": f"Bearer {config.TOKEN_WHATSAPP}"}
    try:
        res_info = requests.get(url_info, headers=headers, timeout=30)
        if res_info.status_code != 200:
            return None, None
        datos_media = res_info.json()
        url_descarga = datos_media.get("url")
        mime_type = datos_media.get("mime_type")
        if not url_descarga:
            return None, None
        res_archivo = requests.get(url_descarga, headers=headers, timeout=60)
        if res_archivo.status_code == 200:
            return res_archivo.content, mime_type
    except requests.RequestException as e:
        logger.error("Error descargando media: %s", e)
    return None, None
