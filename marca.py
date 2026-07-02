"""Crecimiento y marca: blog Inpulso, contexto para la IA."""

ARTICULOS_BLOG = [
    {
        "titulo": "Estrategias de relajación y manejo del estrés",
        "url": "https://inpulso43.com/blog.php",
        "keywords": ("estrés", "estres", "relajación", "relajacion", "agobiad", "ansiedad", "ansios"),
    },
    {
        "titulo": "Ataques de pánico",
        "url": "https://inpulso43.com/blog.php",
        "keywords": ("pánico", "panico", "ataque de pánico", "ataque de panico"),
    },
    {
        "titulo": "Depresión estacional",
        "url": "https://inpulso43.com/blog.php",
        "keywords": ("depresión", "depresion", "tristeza", "ánimo bajo", "animo bajo"),
    },
    {
        "titulo": "Cambios emocionales en el embarazo",
        "url": "https://inpulso43.com/blog.php",
        "keywords": ("embarazo", "embarazada", "maternidad", "postparto"),
    },
    {
        "titulo": "Estrés laboral y burnout",
        "url": "https://inpulso43.com/blog.php",
        "keywords": ("burnout", "trabajo", "laboral", "jefe", "oficina"),
    },
    {
        "titulo": "Bullying y salud mental",
        "url": "https://inpulso43.com/blog.php",
        "keywords": ("bullying", "acoso escolar", "mi hijo", "hija"),
    },
    {
        "titulo": "Amistades tóxicas",
        "url": "https://inpulso43.com/blog.php",
        "keywords": ("amistad tóxica", "amistades toxicas", "amiga tóxica", "amigo tóxico"),
    },
    {
        "titulo": "El síndrome del impostor",
        "url": "https://inpulso43.com/blog.php",
        "keywords": ("síndrome del impostor", "sindrome del impostor", "no soy suficiente"),
    },
]


def contexto_blog_si_aplica(texto: str) -> str:
    """Sugiere a la IA un artículo del blog cuando el tema encaja."""
    t = texto.lower()
    for art in ARTICULOS_BLOG:
        if any(k in t for k in art["keywords"]):
            return (
                f"[Sistema: Recurso de marca — Si encaja con naturalidad, puedes mencionar "
                f"el artículo del blog de Inpulso 43 «{art['titulo']}» ({art['url']}). "
                f"Una frase cálida basta; no fuerces el enlace.]\n"
            )
    return ""
