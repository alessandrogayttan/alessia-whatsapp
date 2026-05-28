import hashlib
import hmac
import json
import logging

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


def enviar_mensaje_whatsapp(telefono_destino: str, texto: str) -> bool:
    telefono_destino = normalizar_telefono(telefono_destino)
    url = f"https://graph.facebook.com/v19.0/{config.ID_TELEFONO}/messages"
    headers = {
        "Authorization": f"Bearer {config.TOKEN_WHATSAPP}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": telefono_destino,
        "type": "text",
        "text": {"body": texto},
    }
    try:
        res = requests.post(url, headers=headers, data=json.dumps(data), timeout=30)
        if res.status_code != 200:
            logger.error("WhatsApp API error %s: %s", res.status_code, res.text)
            return False
        return True
    except requests.RequestException as e:
        logger.error("Error enviando mensaje WhatsApp: %s", e)
        return False


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
