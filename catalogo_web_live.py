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
    """Parsea la sección viva del taller Sanando heridas (fechas, precios, cupo)."""
    meta: dict[str, str] = {}
    texto = _limpiar_html(html_text)
    bajo = texto.lower()

    if "lista de espera" in bajo and "inscripciones abiertas" not in bajo:
        meta["cupo"] = "Lista de espera abierta — escribir HISTORIA por WhatsApp"
        meta["inscripcion"] = (
            "Escribir HISTORIA por WhatsApp para unirse a la lista de espera"
        )
    elif "inscripciones abiertas" in bajo:
        meta["cupo"] = "Inscripciones abiertas — presencial cupo máx. 100 · mayores de 18 años"
        meta["inscripcion"] = (
            "Escríbenos por WhatsApp para apartar tu lugar. "
            "Se aparta con el 50%; liquidar antes del 4 sep 2026."
        )

    # Fechas / modalidades desde facts o copy visible
    if re.search(r"presencial\s*6\s*sep", bajo) and re.search(
        r"online\s*(desde\s*)?8\s*sep", bajo
    ):
        meta["fechas"] = "Presencial 6 sep 2026 · Online desde 8 sep 2026 (5 semanas)"
        meta["horario"] = "Presencial 9:00–18:00 · Online mar/jue 19:00–20:30 (CDMX)"
        meta["modalidad"] = (
            "Presencial en Zapopan (Agua Azul 3008, La Palmira) + online en vivo (Zoom)"
        )

    # Precios: prioriza el resumen FAQ si existe
    m_faq = re.search(
        r"Presencial:\s*regular\s*\$?\s*1[,.]?200\s*/\s*preventa\s*\$?\s*1[,.]?000[^.]*\."
        r"\s*Online:\s*regular\s*\$?\s*1[,.]?000\s*/\s*preventa\s*\$?\s*900[^.]*\.",
        texto,
        re.I,
    )
    if m_faq:
        meta["precio"] = re.sub(r"\s+", " ", m_faq.group(0)).strip()
    elif "$1,200" in texto or "$1.200" in texto or "1,200 MXN" in texto:
        meta["precio"] = (
            "Presencial: preventa $1,000 / regular $1,200 "
            "(dúo $950, grupos 4+ $900). "
            "Online: preventa $900 / regular $1,000 "
            "(dúo $800, grupos 4+ $750). "
            "Preventa hasta el 6 ago 2026 o primeros 20 lugares por modalidad."
        )

    chips = re.findall(r'class="heridas-premium__chip"[^>]*>([^<]+)', html_text)
    if chips:
        meta["chips"] = [c.strip() for c in chips if c.strip()]  # type: ignore[assignment]

    facts = re.findall(
        r'class="heridas-premium__fact"[^>]*>\s*(.*?)\s*</div>',
        html_text,
        re.I | re.S,
    )
    if facts:
        limpios = [_limpiar_html(f) for f in facts]
        meta["facts"] = [f for f in limpios if f]  # type: ignore[assignment]

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
    heridas = _extraer_meta_heridas(html_text)
    if heridas:
        talleres.setdefault("sanando-heridas", {"id_web": "sanando-heridas"})
        talleres["sanando-heridas"].update(heridas)

    _CACHE["talleres"] = talleres
    _CACHE["ts"] = ahora
    return talleres


def invalidar_cache_web():
    _CACHE["talleres"] = None
    _CACHE["ts"] = 0.0
