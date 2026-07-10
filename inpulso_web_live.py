"""Contenido en vivo de inpulso43.com para Alessia (caché + búsqueda por tema)."""
from __future__ import annotations

import html
import logging
import os
import re
import time
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)

_CACHE_TTL = int(os.getenv("INPULSO_WEB_CACHE_SECONDS", "300"))
_MAX_CONTEXT_CHARS = int(os.getenv("INPULSO_WEB_CONTEXT_CHARS", "3800"))
_MAX_TOOL_CHARS = int(os.getenv("INPULSO_WEB_TOOL_CHARS", "12000"))

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "Alessia-Inpulso-WebLive/1.0"

_PAGINAS: dict[str, str] = {
    "inicio": "index.php",
    "talleres": "talleres.php",
    "nosotros": "nosotros.php",
    "blog": "blog.php",
    "podcast": "podcast.php",
    "contacto": "contacto.php",
}

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "talleres": (
        "taller",
        "talleres",
        "curso",
        "cursos",
        "club",
        "heridas",
        "capítulos",
        "capitulos",
        "lectura",
        "alianza",
        "encontrarnos",
        "biblioteca",
        "inscri",
        "lista de espera",
        "historia",
    ),
    "nosotros": (
        "equipo",
        "terapeuta",
        "terapeutas",
        "psicolog",
        "nutrici",
        "médic",
        "medic",
        "doctor",
        "sara",
        "juan",
        "ivan",
        "iván",
        "gabriela",
        "patricia",
        "paty",
        "rebeca",
        "betty",
        "magui",
        "marcela",
        "especialista",
        "quién es",
        "quien es",
    ),
    "blog": ("blog", "artículo", "articulo", "publicación", "publicacion", "leer"),
    "podcast": ("podcast", "episodio", "audio", "spotify"),
    "contacto": (
        "contacto",
        "dirección",
        "direccion",
        "ubicación",
        "ubicacion",
        "ubicad",
        "dónde están",
        "donde están",
        "donde estan",
        "mapa",
        "teléfono",
        "telefono",
        "llamar",
        "whatsapp",
        "horario de atención",
        "horario de atencion",
        "estacionamiento",
        "cómo llegar",
        "como llegar",
    ),
    "inicio": (
        "inpulso",
        "clínica",
        "clinica",
        "qué es",
        "que es",
        "servicios",
        "bienestar",
        "mentor",
        "mentora",
        "360",
        "iniciar",
        "empezar",
    ),
}

_page_cache: dict[str, dict[str, Any]] = {}


def _limpiar_html(texto: str) -> str:
    t = html.unescape(texto or "")
    t = re.sub(r"<script[^>]*>.*?</script>", " ", t, flags=re.I | re.S)
    t = re.sub(r"<style[^>]*>.*?</style>", " ", t, flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _extraer_pagina(html_text: str, url: str) -> dict[str, Any]:
    title_m = re.search(r"<title[^>]*>([^<]+)", html_text, re.I)
    title = html.unescape(title_m.group(1).strip()) if title_m else ""

    def heads(tag: str, limit: int = 20) -> list[str]:
        out = []
        for x in re.findall(rf"<{tag}[^>]*>(.*?)</{tag}>", html_text, re.I | re.S):
            t = _limpiar_html(x)
            if 2 < len(t) < 220:
                out.append(t)
            if len(out) >= limit:
                break
        return out

    precios = sorted(set(re.findall(r"\$[\d,]+(?:\s*MXN)?", html_text)))[:25]
    fechas = list(
        dict.fromkeys(
            re.findall(
                r"(?:\d{1,2}\s+de\s+\w+\s+de\s+\d{4}|"
                r"Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)[^.]{0,90}",
                html_text,
                re.I,
            )
        )
    )[:12]
    listas = []
    for x in re.findall(r"<li[^>]*>(.*?)</li>", html_text, re.I | re.S):
        t = _limpiar_html(x)
        if 8 < len(t) < 280:
            listas.append(t)
        if len(listas) >= 30:
            break

    texto = _limpiar_html(html_text)
    return {
        "url": url,
        "title": title,
        "h1": heads("h1", 6),
        "h2": heads("h2", 12),
        "h3": heads("h3", 15),
        "precios": precios,
        "fechas": fechas,
        "listas": listas,
        "texto": texto[: _MAX_TOOL_CHARS],
        "fetched_at": time.time(),
    }


def _fetch_pagina(clave: str, *, forzar: bool = False) -> dict[str, Any]:
    if clave not in _PAGINAS:
        return {"error": f"Página desconocida: {clave}"}

    cached = _page_cache.get(clave)
    if (
        not forzar
        and cached
        and time.time() - cached.get("fetched_at", 0) < _CACHE_TTL
    ):
        return cached

    url = f"{config.CLINICA_WEB_URL.rstrip('/')}/{_PAGINAS[clave]}"
    try:
        res = _SESSION.get(url, timeout=25)
        res.raise_for_status()
        data = _extraer_pagina(res.text, url)
        _page_cache[clave] = data
        return data
    except Exception as e:
        logger.warning("No se pudo leer %s: %s", url, e)
        if cached:
            return cached
        return {"url": url, "error": str(e), "fetched_at": time.time()}


def paginas_relevantes(consulta: str) -> list[str]:
    """Ordena páginas por relevancia a la consulta del paciente."""
    q = (consulta or "").lower()
    scores: dict[str, int] = {k: 0 for k in _PAGINAS}
    for clave, palabras in _KEYWORDS.items():
        for palabra in palabras:
            if palabra in q:
                scores[clave] += 2 if len(palabra) > 5 else 1

    ordenadas = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    elegidas = [k for k, s in ordenadas if s > 0]
    if not elegidas:
        return ["inicio", "talleres", "nosotros"]
    if "inicio" not in elegidas:
        elegidas.append("inicio")
    return elegidas[:3]


def _formatear_pagina_corta(clave: str, data: dict[str, Any], max_chars: int) -> str:
    if data.get("error"):
        return f"[{clave}] error leyendo sitio: {data['error']}"
    partes = [f"=== {clave.upper()} ({data.get('url', '')}) ==="]
    if data.get("title"):
        partes.append(f"Título: {data['title']}")
    if data.get("h1"):
        partes.append("Encabezados: " + " | ".join(data["h1"][:4]))
    if data.get("h2"):
        partes.append("Secciones: " + " | ".join(data["h2"][:8]))
    if data.get("precios"):
        partes.append("Precios en página: " + ", ".join(data["precios"][:12]))
    if data.get("fechas"):
        partes.append("Fechas mencionadas: " + " | ".join(data["fechas"][:6]))
    if data.get("listas"):
        partes.append("Listas: " + " • ".join(data["listas"][:10]))
    texto = data.get("texto", "")
    if texto:
        restante = max_chars - len(" ".join(partes))
        if restante > 200:
            partes.append("Contenido: " + texto[:restante])
    bloque = "\n".join(partes)
    return bloque[:max_chars]


def _formatear_pagina_completa(clave: str, data: dict[str, Any]) -> str:
    if data.get("error"):
        return f"No pude leer {clave}: {data['error']}"
    partes = [
        f"PÁGINA: {clave} — {data.get('url', '')}",
        f"Título: {data.get('title', '')}",
    ]
    for campo, etiqueta in (
        ("h1", "H1"),
        ("h2", "H2"),
        ("h3", "H3"),
        ("precios", "Precios"),
        ("fechas", "Fechas"),
        ("listas", "Viñetas"),
    ):
        vals = data.get(campo) or []
        if vals:
            partes.append(f"{etiqueta}: " + " | ".join(str(v) for v in vals))
    if data.get("texto"):
        partes.append("TEXTO COMPLETO (extraído del HTML público):\n" + data["texto"])
    return "\n".join(partes)[:_MAX_TOOL_CHARS]


def obtener_contexto_web_en_vivo(pista: str = "") -> str:
    """Resumen automático del sitio para inyectar en cada mensaje."""
    if not config.ENABLE_INPULSO_WEB_LIVE:
        return ""

    paginas = paginas_relevantes(pista)
    presupuesto = _MAX_CONTEXT_CHARS // max(len(paginas), 1)
    bloques = [
        "[Sistema: WEB VIVA inpulso43.com — fuente oficial actualizada; "
        "prioriza esto sobre catálogos locales si hay diferencia]\n"
    ]
    for clave in paginas:
        data = _fetch_pagina(clave)
        bloques.append(_formatear_pagina_corta(clave, data, presupuesto))

    return "\n".join(bloques)[: _MAX_CONTEXT_CHARS + 400] + "\n"


def consultar_sitio_inpulso(consulta: str, pagina: str = "auto") -> str:
    """
    Lee inpulso43.com en vivo y devuelve contenido público actualizado.
    pagina: auto | inicio | talleres | nosotros | blog | podcast | contacto
    """
    consulta = (consulta or "").strip()
    if pagina and pagina.lower() not in ("auto", ""):
        clave = pagina.lower().strip()
        if clave not in _PAGINAS:
            claves = ", ".join(_PAGINAS)
            return f"Página no válida. Usa: auto o una de: {claves}"
        data = _fetch_pagina(clave, forzar=True)
        return (
            f"Consulta del paciente: {consulta or '(general)'}\n\n"
            + _formatear_pagina_completa(clave, data)
            + "\n\nINSTRUCCIÓN PARA LA IA: Responde con esta información oficial del sitio. "
            "Si algo no aparece aquí, dilo con honestidad y ofrece contacto o WhatsApp."
        )

    claves = paginas_relevantes(consulta)
    bloques = [f"Consulta: {consulta or '(general)'}\n"]
    for clave in claves:
        data = _fetch_pagina(clave, forzar=True)
        bloques.append(_formatear_pagina_completa(clave, data))
    return (
        "\n\n---\n\n".join(bloques)
        + "\n\nINSTRUCCIÓN PARA LA IA: Usa solo datos de estas páginas oficiales. "
        "Combina con empatía; no inventes precios, fechas ni nombres que no aparezcan aquí."
    )


def invalidar_cache_web_live():
    _page_cache.clear()
