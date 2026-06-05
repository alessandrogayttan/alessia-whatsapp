"""Análisis exhaustivo de inpulso43.com — rutas, navegación y contenido."""
import re
import sys
from html import unescape
from urllib.parse import urljoin, urlparse

import requests

BASE = "https://inpulso43.com"
BASE_WWW = "https://www.inpulso43.com"
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
)


def fetch(url: str) -> tuple[int, str, str]:
    try:
        r = SESSION.get(url, timeout=25, allow_redirects=True)
        return r.status_code, r.url, r.text
    except requests.RequestException as e:
        return 0, url, str(e)


def extraer_enlaces(html: str, base_url: str) -> set[str]:
    links = set()
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
        href = m.group(1).strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if "inpulso43.com" in parsed.netloc or parsed.netloc == "":
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
            if parsed.query:
                clean += "?" + parsed.query
            links.add(clean or base_url)
    return links


def extraer_ids_secciones(html: str) -> list[str]:
    ids = []
    for m in re.finditer(r'\bid=["\']([^"\']+)["\']', html):
        ids.append(m.group(1))
    return sorted(set(ids))


def extraer_nav_texto(html: str) -> list[str]:
    items = []
    for m in re.finditer(r"<nav[^>]*>(.*?)</nav>", html, re.I | re.S):
        nav = m.group(1)
        for a in re.finditer(r"<a[^>]*>([^<]+)</a>", nav, re.I):
            t = unescape(re.sub(r"\s+", " ", a.group(1)).strip())
            if t:
                items.append(t)
    for m in re.finditer(r'class=["\'][^"\']*nav[^"\']*["\'][^>]*>([^<]{2,80})', html, re.I):
        t = unescape(m.group(1).strip())
        if t and len(t) < 60:
            items.append(t)
    return list(dict.fromkeys(items))


def resumir_pagina(url: str, html: str) -> dict:
    title = ""
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if m:
        title = unescape(m.group(1).strip())

    h1 = [unescape(x.strip()) for x in re.findall(r"<h1[^>]*>([^<]+)", html, re.I)]
    h2 = [unescape(x.strip()) for x in re.findall(r"<h2[^>]*>([^<]+)", html, re.I)]
    h3 = [unescape(x.strip()) for x in re.findall(r"<h3[^>]*>([^<]+)", html, re.I)]

    # data-page, router paths en JS
    rutas_js = sorted(
        set(
            re.findall(
                r'["\']/(?:talleres|servicios|psicologia|nutricion|medicina|equipo|contacto|nosotros|blog|agenda)[^"\']*["\']',
                html,
                re.I,
            )
        )
    )

    return {
        "url": url,
        "title": title,
        "h1": h1[:5],
        "h2": h2[:12],
        "h3": h3[:15],
        "ids": extraer_ids_secciones(html)[:30],
        "rutas_js": rutas_js[:20],
        "len": len(html),
    }


def probar_rutas_comunes() -> list[tuple[str, int, str]]:
    candidatas = [
        "/",
        "/talleres",
        "/servicios",
        "/psicologia",
        "/nutricion",
        "/medicina",
        "/equipo",
        "/nosotros",
        "/contacto",
        "/agenda",
        "/citas",
        "/blog",
        "/amigas-en-la-palabra",
        "/iniciativas",
        "/privacidad",
        "/aviso-de-privacidad",
        "/terminos",
        "/index.html",
        "/home",
        "/es",
        "/es/talleres",
        "/talleres/",
        "/servicios/",
        "/pages/talleres",
        "/page/talleres",
    ]
    resultados = []
    vistos = set()
    for path in candidatas:
        for base in (BASE, BASE_WWW):
            url = base + path if path != "/" else base + "/"
            if url in vistos:
                continue
            vistos.add(url)
            code, final, html = fetch(url)
            resultados.append((final, code, html[:200] if isinstance(html, str) else ""))
    return resultados


def main():
    print("=" * 60)
    print("ANÁLISIS inpulso43.com")
    print("=" * 60)

    code, final_url, html = fetch(BASE)
    print(f"\nHome: {code} -> {final_url} ({len(html)} bytes)")

    if code != 200:
        print("No se pudo cargar la home.")
        sys.exit(1)

    enlaces = extraer_enlaces(html, final_url)
    print(f"\n--- ENLACES INTERNOS ({len(enlaces)}) ---")
    for link in sorted(enlaces):
        print(" ", link)

    print("\n--- NAVEGACIÓN ---")
    for item in extraer_nav_texto(html):
        print(" ", item)

    resumen = resumir_pagina(final_url, html)
    print("\n--- HOME: TÍTULOS ---")
    print(" title:", resumen["title"])
    print(" h1:", resumen["h1"])
    print(" h2:", resumen["h2"])
    print(" h3:", resumen["h3"])
    if resumen["ids"]:
        print(" section ids:", resumen["ids"][:20])
    if resumen["rutas_js"]:
        print(" rutas en JS:", resumen["rutas_js"])

    # sitemap / robots
    for extra in ("/sitemap.xml", "/robots.txt", "/sitemap_index.xml"):
        c, u, t = fetch(BASE + extra)
        print(f"\n{extra}: HTTP {c}")
        if c == 200 and len(t) < 8000:
            print(t[:2000])

    print("\n--- PROBANDO RUTAS COMUNES ---")
    hashes = {}
    for url, status, snippet in probar_rutas_comunes():
        if status != 200:
            print(f"  [{status}] {url}")
            continue
        # fingerprint por título + primer h1
        m = re.search(r"<title[^>]*>([^<]+)", snippet) or re.search(r"<title[^>]*>([^<]+)", fetch(url)[2])
        title = m.group(1) if m else "?"
        key = (status, title[:40], len(snippet))
        if url not in hashes:
            _, _, full = fetch(url)
            hashes[url] = hash(full[:5000])
        print(f"  [200] {url}  hash={hashes[url]}")

    # Comparar si rutas devuelven HTML distinto
    print("\n--- ¿PÁGINAS DISTINTAS? (hash contenido) ---")
    unicos = {}
    for url, h in hashes.items():
        unicos.setdefault(h, []).append(url)
    for h, urls in unicos.items():
        print(f"  Grupo ({len(urls)} URLs): {urls[0]}" + (f" +{len(urls)-1} más" if len(urls) > 1 else ""))

    # Buscar archivos JS con rutas
    print("\n--- SCRIPTS ---")
    for m in re.finditer(r'<script[^>]+src=["\']([^"\']+)["\']', html):
        src = urljoin(final_url, m.group(1))
        if "inpulso" in src or src.startswith("/"):
            print(" ", src)

    # anchor sections en misma página
    anchors = sorted(set(re.findall(r'href=["\']#([^"\']+)["\']', html)))
    if anchors:
        print(f"\n--- ANCHORS EN HOME ({len(anchors)}) ---")
        for a in anchors[:40]:
            print(" ", "#" + a)


if __name__ == "__main__":
    main()
