"""Crecimiento y marca: referidos, blog Inpulso, contexto para la IA."""
import config

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


def mensaje_codigo_referido(telefono: str) -> str:
    import storage

    codigo = storage.obtener_o_crear_codigo_referido(telefono)
    nombre = storage.primer_nombre(telefono)
    saludo = f"¡Hola {nombre}! " if nombre else ""
    return (
        f"{saludo}💜 *Invita a alguien a Inpulso 43*\n\n"
        f"Tu código personal: *{codigo}*\n\n"
        f"Si un amigo escribe ese código al contactarnos, recibe "
        f"*{config.REFERIDO_DESCUENTO}* (aplican políticas en recepción).\n\n"
        f"🌐 {config.CLINICA_WEB_URL}"
    )


def mensaje_referido_tras_nps_alto(telefono: str) -> str:
    import storage

    codigo = storage.obtener_o_crear_codigo_referido(telefono)
    return (
        f"💜 *Gracias por tu confianza*\n\n"
        f"Si conoces a alguien que podría beneficiarse de Inpulso 43, "
        f"comparte tu código: *{codigo}*\n\n"
        f"Tu amigo recibe {config.REFERIDO_DESCUENTO} y tú ayudas a que más "
        f"personas cuiden su bienestar ✨"
    )


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
