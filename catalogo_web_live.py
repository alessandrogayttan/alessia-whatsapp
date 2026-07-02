"""Lee talleres publicados en inpulso43.com/talleres.php (caché corta)."""
from __future__ import annotations

import html
import logging
import re
import time
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"talleres": None, "ts": 0.0}
_CACHE_TTL = int(__import__("os").getenv("CATALOGO_WEB_CACHE_SECONDS", "300"))


def _limpiar_html(texto: str) -> str:
    t = html.unescape(texto or "")
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _extraer_bloques_js(html_text: str) -> dict[str, dict]:
    talleres: dict[str, dict] = {}
    for m in re.finditer(r"'([a-z0-9-]+)'\s*:\s*\{", html_text):
        wid = m.group(1)
        chunk = html_text[m.start() : m.start() + 4000]
        title = re.search(r"title:\s*'([^']*)'", chunk)
        instructor = re.search(r"instructor:\s*'([^']*)'", chunk)
        desc = re.search(r"desc:\s*'((?:\\'|[^'])*)'", chunk, re.S)
        if not title:
            continue
        talleres[wid] = {
            "id_web": wid,
            "nombre": _limpiar_html(title.group(1)),
            "instructor": _limpiar_html(instructor.group(1)) if instructor else "",
            "descripcion_js": _limpiar_html(desc.group(1)) if desc else "",
        }
    return talleres


def _extraer_meta_heridas(html_text: str) -> dict:
    meta = {}
    if "Lista de espera abierta" in html_text:
        meta["cupo"] = "Lista de espera abierta — escribir HISTORIA por WhatsApp"
    m = re.search(
        r"heridas-premium__chip[^>]*>\s*([^<]+(?:agosto|enero|febrero|marzo|abril|mayo|junio|julio|septiembre|octubre|noviembre|diciembre)[^<]*)",
        html_text,
        re.I,
    )
    if m:
        meta["fechas"] = re.sub(r"\s+", " ", m.group(1)).strip()
    chips = re.findall(r'class="heridas-premium__chip"[^>]*>([^<]+)', html_text)
    if chips:
        meta["chips"] = [c.strip() for c in chips if c.strip()]
    return meta


def cargar_talleres_publicados_web(*, forzar: bool = False) -> dict[str, dict]:
    """Devuelve {id_web: datos parseados} desde talleres.php."""
    ahora = time.time()
    if (
        not forzar
        and _CACHE["talleres"] is not None
        and ahora - _CACHE["ts"] < _CACHE_TTL
    ):
        return _CACHE["talleres"]

    url = f"{config.CLINICA_WEB_URL.rstrip('/')}/talleres.php"
    try:
        res = requests.get(
            url,
            timeout=25,
            headers={"User-Agent": "Alessia-Inpulso-Catalogo/1.0"},
        )
        res.raise_for_status()
        html_text = res.text
    except Exception as e:
        logger.warning("No se pudo leer talleres.php: %s", e)
        return _CACHE["talleres"] or {}

    talleres = _extraer_bloques_js(html_text)
    if "sanando-heridas" in talleres:
        talleres["sanando-heridas"].update(_extraer_meta_heridas(html_text))

    _CACHE["talleres"] = talleres
    _CACHE["ts"] = ahora
    return talleres


def invalidar_cache_web():
    _CACHE["talleres"] = None
    _CACHE["ts"] = 0.0
