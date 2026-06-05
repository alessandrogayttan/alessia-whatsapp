"""Extrae contenido de todas las páginas PHP de inpulso43.com."""
import json
import re
import sys
from html import unescape
from pathlib import Path

import requests

BASE = "https://inpulso43.com"
PAGINAS = [
    "index.php",
    "talleres.php",
    "nosotros.php",
    "blog.php",
    "podcast.php",
    "contacto.php",
]

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "Mozilla/5.0 (compatible; AlessiaBot/1.0)"


def texto_limpio(html: str) -> str:
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.I | re.S)
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))).strip()


def extraer(html: str) -> dict:
    title = ""
    m = re.search(r"<title[^>]*>([^<]+)", html, re.I)
    if m:
        title = unescape(m.group(1).strip())

    def heads(tag):
        return [
            unescape(re.sub(r"\s+", " ", x).strip())
            for x in re.findall(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.I | re.S)
            if len(x.strip()) < 200
        ]

    h1 = heads("h1")
    h2 = heads("h2")
    h3 = heads("h3")
    h4 = heads("h4")

    # Cards / talleres
    cards = []
    for m in re.finditer(
        r'class=["\'][^"\']*(?:card|taller|workshop|curso)[^"\']*["\'][^>]*>(.*?)</(?:div|article|section)>',
        html,
        re.I | re.S,
    ):
        t = texto_limpio(m.group(1))[:400]
        if len(t) > 30:
            cards.append(t)

    # Precios
    precios = re.findall(r"\$[\d,]+(?:\s*MXN)?", html)
    # Fechas
    fechas = re.findall(
        r"(?:Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)[^.]{0,80}",
        html,
        re.I,
    )
    # Listas
    lis = [
        unescape(re.sub(r"\s+", " ", x).strip())
        for x in re.findall(r"<li[^>]*>(.*?)</li>", html, re.I | re.S)
        if 10 < len(x.strip()) < 300
    ]

    return {
        "title": title,
        "h1": h1[:8],
        "h2": h2[:15],
        "h3": h3[:20],
        "h4": h4[:15],
        "precios": sorted(set(precios))[:20],
        "fechas": list(dict.fromkeys(fechas))[:15],
        "listas": lis[:25],
        "cards": cards[:10],
        "texto_muestra": texto_limpio(html)[:2500],
    }


def main():
    out = {}
    for pagina in PAGINAS:
        url = f"{BASE}/{pagina}"
        try:
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            out[pagina] = {"url": url, "status": r.status_code, **extraer(r.text)}
            print(f"OK {pagina} ({len(r.text)} bytes)", file=sys.stderr)
        except Exception as e:
            out[pagina] = {"url": url, "error": str(e)}
            print(f"ERR {pagina}: {e}", file=sys.stderr)

    dest = Path(__file__).parent / "inpulso_web_contenido.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(dest))


if __name__ == "__main__":
    main()
