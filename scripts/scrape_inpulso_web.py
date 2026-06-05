"""Extrae contenido público de inpulso43.com para sincronizar catálogo."""
import re
from html import unescape

import requests

URL = "https://inpulso43.com"


def main():
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    t = r.text

    print("=== SLIDES (especialidades) ===")
    for m in re.finditer(r'slide-title[^>]*>([^<]+)', t):
        print(" -", unescape(m.group(1).strip()))
    for m in re.finditer(r'slide-desc[^>]*>([^<]+)', t):
        print("   ", unescape(m.group(1).strip()))

    print("\n=== TALLER HERO ===")
    idx = t.find("hero-taller-tab")
    if idx >= 0:
        block = t[idx : idx + 2500]
        text = unescape(re.sub(r"<[^>]+>", "\n", block))
        for line in text.splitlines():
            line = line.strip()
            if line and len(line) > 3:
                print(line)

    print("\n=== H3 ===")
    for m in re.finditer(r"<h3[^>]*>([^<]+)", t):
        print(" -", unescape(m.group(1).strip()))

    print("\n=== LINKS INTERNOS ===")
    seen = set()
    for m in re.finditer(r'href="([^"]+)"', t):
        u = m.group(1)
        if u.startswith("/") or "inpulso43" in u:
            if u not in seen and u not in ("/", "#"):
                seen.add(u)
                print(" -", u)


if __name__ == "__main__":
    main()
