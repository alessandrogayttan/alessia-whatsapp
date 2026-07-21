"""Serialización de contenido IA (texto o multimodal) para la cola durable."""
from __future__ import annotations

import json
import logging

import storage

logger = logging.getLogger(__name__)

_MM_KEY = "_mm"


def serializar_contenido(contenido) -> tuple[str, int | None]:
    """
    Devuelve (payload_texto_cola, media_id_opcional).
    media_id se borra tras procesar con éxito.
    """
    if isinstance(contenido, str):
        return contenido, None

    if not isinstance(contenido, list):
        return str(contenido), None

    texto_parts: list[str] = []
    media_id = None
    mime = "application/octet-stream"
    data = b""

    for part in contenido:
        text = getattr(part, "text", None)
        if text:
            texto_parts.append(text)
        inline = getattr(part, "inline_data", None)
        if inline is not None:
            mime = getattr(inline, "mime_type", None) or mime
            raw = getattr(inline, "data", None)
            if raw:
                data = raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)
                media_id = storage.guardar_cola_media(mime, bytes(data))

    payload = json.dumps(
        {_MM_KEY: 1, "media_id": media_id, "mime": mime, "texto": "\n".join(texto_parts)},
        ensure_ascii=False,
    )
    return payload, media_id


def deserializar_contenido(payload: str):
    """Reconstruye str o lista de Parts para Gemini."""
    texto = payload or ""
    if not texto.startswith("{") or f'"{_MM_KEY}"' not in texto[:40]:
        return texto
    try:
        data = json.loads(texto)
    except json.JSONDecodeError:
        return texto
    if not data.get(_MM_KEY):
        return texto

    from google.genai import types

    partes = []
    media_id = data.get("media_id")
    if media_id:
        row = storage.obtener_cola_media(int(media_id))
        if row:
            mime_type, blob = row
            partes.append(
                types.Part(inline_data=types.Blob(data=blob, mime_type=mime_type))
            )
        else:
            logger.warning("cola_media id=%s no encontrado", media_id)
    if data.get("texto"):
        partes.append(types.Part(text=data["texto"]))
    return partes or (data.get("texto") or "")


def media_id_de_payload(payload: str) -> int | None:
    if not (payload or "").startswith("{") or f'"{_MM_KEY}"' not in (payload or "")[:40]:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    mid = data.get("media_id")
    return int(mid) if mid else None
