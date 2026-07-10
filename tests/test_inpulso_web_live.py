"""Tests inpulso43.com en vivo."""
import inpulso_web_live as live


SAMPLE_HTML = """
<html><head><title>Inpulso 43 Talleres</title></head>
<body>
<h1>Biblioteca Inpulso</h1>
<h2>Sanando tus heridas del pasado</h2>
<p>Taller con Sara Rosales. Inicio 30 agosto 2026.</p>
<li>Lista de espera abierta</li>
<p>Precio $400 MXN</p>
</body></html>
"""


def test_paginas_relevantes_talleres():
    paginas = live.paginas_relevantes("¿cuándo empieza el taller de heridas?")
    assert "talleres" in paginas


def test_paginas_relevantes_contacto():
    paginas = live.paginas_relevantes("¿dónde están ubicados?")
    assert "contacto" in paginas


def test_extraer_pagina_limpia_datos():
    data = live._extraer_pagina(SAMPLE_HTML, "https://inpulso43.com/talleres.php")
    assert "Biblioteca Inpulso" in data["h1"][0]
    assert any("heridas" in h.lower() for h in data["h2"])
    assert "$400" in " ".join(data["precios"])


def test_obtener_contexto_web_en_vivo(monkeypatch):
    monkeypatch.setattr(
        live,
        "_fetch_pagina",
        lambda clave, forzar=False: {
            "url": f"https://inpulso43.com/{clave}.php",
            "title": "Test",
            "h1": ["Hola"],
            "h2": [],
            "precios": [],
            "fechas": [],
            "listas": [],
            "texto": "Contenido de prueba del sitio.",
            "fetched_at": 0,
        },
    )
    ctx = live.obtener_contexto_web_en_vivo("talleres disponibles")
    assert "WEB VIVA" in ctx
    assert "Contenido de prueba" in ctx


def test_consultar_sitio_inpulso_tool(monkeypatch):
    monkeypatch.setattr(
        live,
        "_fetch_pagina",
        lambda clave, forzar=False: live._extraer_pagina(
            SAMPLE_HTML, "https://inpulso43.com/talleres.php"
        ),
    )
    out = live.consultar_sitio_inpulso("precio taller heridas", "talleres")
    assert "Sanando" in out or "heridas" in out.lower()
    assert "INSTRUCCIÓN PARA LA IA" in out


def test_tools_consultar_sitio_wrapper(monkeypatch):
    from tools import consultar_sitio_inpulso

    monkeypatch.setattr(
        "inpulso_web_live.consultar_sitio_inpulso",
        lambda c, p="auto": f"OK:{c}:{p}",
    )
    assert consultar_sitio_inpulso("hola", "inicio") == "OK:hola:inicio"
