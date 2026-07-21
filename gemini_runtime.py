"""Cliente Gemini compartido y envío con timeout (WhatsApp / web / equipo)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from google import genai

import config

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def get_genai_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY no configurada")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def send_message_con_timeout(chat, contenido, timeout: int = 120):
    """Evita hilos colgados sin respuesta ante latencia de Gemini."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(chat.send_message, contenido)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout:
            future.cancel()
            raise
