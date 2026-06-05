"""Extrae datos estructurados de talleres.php."""
import json
import re
from pathlib import Path

import requests

OUT = Path(__file__).parent
r = requests.get("https://inpulso43.com/talleres.php", timeout=30)
t = r.text
OUT.joinpath("talleres_raw.html").write_text(t, encoding="utf-8")

scripts = re.findall(r"<script[^>]*>(.*?)</script>", t, re.S)
result = {"scripts_count": len(scripts), "workshop_script": None}

for i, s in enumerate(scripts):
    if any(k in s for k in ("Educar", "Alianza", "biblioteca", "TALLERES")):
        OUT.joinpath(f"talleres_script_{i}.js").write_text(s, encoding="utf-8")
        result["workshop_script"] = i

        # Intentar extraer array de objetos
        for m in re.finditer(r"(\[[\s\S]{500,}?\])\s*;?\s*(?:const|let|var|window\.|document\.)", s):
            blob = m.group(1)
            try:
                data = json.loads(blob)
                result["parsed_array"] = data
                break
            except json.JSONDecodeError:
                pass

        # Buscar asignaciones tipo { id: ..., title: ...}
        objs = []
        for m in re.finditer(
            r"\{\s*id\s*:\s*['\"][^'\"]+['\"][\s\S]{50,2000}?\}",
            s,
        ):
            objs.append(m.group(0)[:1500])
        if objs:
            result["object_snippets"] = objs[:6]

OUT.joinpath("talleres_parsed.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2, default=str),
    encoding="utf-8",
)
