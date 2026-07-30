"""Capa de respuestas fiables: precios, talleres, equipo, FAQ y contacto.

WhatsApp y web usan la misma lógica. Preguntas claras de información
se responden con hechos locales sin depender de Gemini.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import config
from catalogo_web import (
    AREAS_ACOMPANAMIENTO_WEB,
    CONTACTO_WEB,
    EQUIPO_WEB,
    ESPECIALIDADES_INPULSO,
    FAQ_WEB,
    MENSAJE_BASE_WEB,
    METODO_WEB,
    PAGINAS_SITIO,
    id_web_desde_texto,
    obtener_talleres_vigentes,
)
from conocimiento import parece_consulta_informativa

PRECIOS_PATH = Path(__file__).resolve().parent / "precios.json"

_RELLENO = re.compile(
    r"("
    r"dejame revisar|déjame revisar|permiteme|permíteme un momento|"
    r"un momentito|dame un momento|voy a buscar|busco (la )?informaci[oó]n|"
    r"reviso (nuestros )?recursos|estoy buscando|te confirmo en un momento|"
    r"ya lo estoy revisando|d[eé]jame checar|déjame checar|"
    r"un segundo|espera un momento|estoy revisando|lo reviso|"
    r"dame un segundito|ahorita te confirmo"
    r")",
    re.I,
)

_TRAMITE = re.compile(
    r"\b("
    r"agendar|agenda(r|me|mos)?|inscribir(me)?|inscripci[oó]n|"
    r"comprobante|cancelar|reagendar|factura|cfdi|"
    r"hablar con persona|emergencia"
    r")\b",
    re.I,
)

_INFO = re.compile(
    r"("
    r"\?|¿|informaci[oó]n|info|cu[aá]nto|cuesta|precio|precios|costo|costos|"
    r"horario|horarios|cu[aá]ndo|d[oó]nde|qu[eé] es|de qu[eé]|sobre |"
    r"taller|talleres|club|lectura|temario|cupo|modalidad|gratis|gratuito|"
    r"equipo|terapeuta|terapeutas|psic[oó]log|nutrici[oó]n|ubicaci[oó]n|"
    r"direcci[oó]n|contacto|tel[eé]fono|estacionamiento|pago|pagos|"
    r"transferencia|clabe|especialidad|servicios|cat[aá]logo|lista"
    r")",
    re.I,
)

_NOMBRES_PRECIO = {
    "sara": ("sara", "sara rosales"),
    "juan": ("juan", "juan rosales"),
    "patricia": ("patricia", "patricia velazquez", "patricia velázquez"),
    "ivan": ("ivan", "iván", "ivan navarro", "iván navarro"),
    "nutricionista": (
        "nutricion",
        "nutrición",
        "nutriolog",
        "nutriólog",
        "gabriela",
        "gabriela sanchez",
        "gabriela sánchez",
    ),
    "medicina": ("medicina", "medico", "médico", "medica", "médica"),
}

_ETIQUETAS_PRECIO = {
    "sara": "Sara Rosales (psicología)",
    "juan": "Juan Rosales (psicología)",
    "patricia": "Patricia Velázquez (psicología)",
    "ivan": "Iván Navarro (psicología)",
    "nutricionista": "Gabriela Sánchez (nutrición)",
    "medicina": "Medicina familiar",
}


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip()


def extraer_texto_usuario(contenido: Any) -> str:
    if contenido is None:
        return ""
    if isinstance(contenido, str):
        return contenido.strip()
    if isinstance(contenido, list):
        partes = []
        for p in contenido:
            texto = getattr(p, "text", None)
            if texto:
                partes.append(str(texto))
            elif isinstance(p, dict) and p.get("text"):
                partes.append(str(p["text"]))
            elif isinstance(p, str):
                partes.append(p)
        return "\n".join(partes).strip()
    texto = getattr(contenido, "text", None)
    if texto:
        return str(texto).strip()
    return str(contenido).strip()


def _solo_mensaje_paciente(texto: str) -> str:
    """Quita instrucciones de sistema; deja solo lo que escribió el usuario."""
    t = texto or ""
    # Bloques [Sistema: ...] / [Modo staff: ...] aunque vayan en la misma línea
    t = re.sub(r"\[Sistema:[^\]]*\]", " ", t)
    t = re.sub(r"\[Modo staff:[^\]]*\]", " ", t)
    lineas = []
    for linea in t.splitlines():
        s = linea.strip()
        if not s or s.startswith("[Sistema:") or s.startswith("[Modo staff:"):
            continue
        lineas.append(linea)
    limpio = "\n".join(lineas).strip()
    limpio = re.sub(r"[ \t]{2,}", " ", limpio)
    return limpio


_SALUDO_TOKENS = frozenset(
    {
        "hola",
        "holi",
        "hello",
        "hi",
        "hey",
        "saludos",
        "buen",
        "buena",
        "buenas",
        "buenos",
        "dia",
        "dias",
        "tarde",
        "tardes",
        "noche",
        "noches",
        "que",
        "tal",
        "alessia",
        "inpulso",
        "equipo",
        "a",
        "todos",
        "hoy",
        "como",
        "estas",
        "estoy",
        "bien",
        "mal",
        "todo",
        "anda",
        "va",
        "hay",
        "te",
        "tu",
        "usted",
        "amigo",
        "amiga",
    }
)


def _es_solo_saludo(texto: str) -> bool:
    """True si el mensaje es solo un saludo (sin pedir info)."""
    t = _norm(texto)
    t = re.sub(r"[^\w\s]", " ", t)
    palabras = [p for p in t.split() if p]
    if not palabras or len(palabras) > 8 or len(t) > 60:
        return False
    return all(p in _SALUDO_TOKENS for p in palabras)


def _es_charla_casual(texto: str) -> bool:
    """Saludos / cómo estás / gracias — no son consulta de catálogo."""
    if _es_solo_saludo(texto):
        return True
    n = _norm(texto)
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    if not n or len(n) > 80:
        return False
    patrones = (
        r"^(hola|holi|hey|hi|saludos)\b",
        r"\bcomo (estas|esta|te va|te encuentras|andas)\b",
        r"\bque tal\b",
        r"\bgracias\b",
        r"\bmuchas gracias\b",
        r"\bok\b",
        r"\blisto\b",
        r"\bperfecto\b",
        r"\bsi\b$",
        r"\bno\b$",
        r"\bbuena(s)? (tardes|noches|dias)\b",
    )
    # Charla corta sin pedir taller/precio/cita
    if any(re.search(p, n) for p in patrones):
        if re.search(
            r"\b(taller|heridas|precio|cuesta|agendar|cita|inscrib|horario|cupo)\b",
            n,
        ):
            return False
        return True
    return False


def _pide_taller_heridas(texto: str) -> bool:
    """Solo True si el usuario pide explícitamente el taller de heridas."""
    n = _norm(texto)
    return bool(
        re.search(
            r"\b("
            r"heridas?( del pasado)?|"
            r"sanando|"
            r"nino interior|niño interior|"
            r"taller de heridas|taller heridas"
            r")\b",
            n,
        )
    )


def es_respuesta_relleno(texto: str) -> bool:
    t = (texto or "").strip()
    if not t:
        return True
    if not _RELLENO.search(t):
        return False
    hechos = re.search(
        r"("
        r"\$\s*\d|mxn|gratis|gratuito|viernes|lunes|martes|mi[eé]rcoles|jueves|"
        r"s[aá]bado|domingo|\d{1,2}:\d{2}|\d{1,2}\s*(am|pm)|mente en cap[ií]tulos|"
        r"sanando|alianza 360|clabe|banorte|zapopan|hidalgo|individual|pareja"
        r")",
        t,
        re.I,
    )
    return hechos is None


def _cargar_precios() -> dict:
    try:
        with open(PRECIOS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


def _parece_pregunta_info(texto: str) -> bool:
    # Trámite puro (agendar sin pedir info) → Gemini
    if _TRAMITE.search(texto) and not re.search(
        r"precio|precios|cuesta|cu[aá]nto|costo|informaci[oó]n|info\b",
        texto,
        re.I,
    ):
        return False
    if parece_consulta_informativa(texto):
        return True
    return bool(_INFO.search(texto))


def _formatear_taller_heridas(t: dict) -> str:
    """Ficha corta del taller heridas (cabe en 1 mensaje + botones)."""
    url = (t.get("url_web") or PAGINAS_SITIO.get("talleres", "") or "").strip()
    return (
        "✨ *Sanando tus heridas del pasado*\n"
        "Con *Juan y Sara Rosales*\n\n"
        "Taller vivencial para entender cómo tu historia sigue hablando en "
        "tus relaciones, miedos y decisiones — y dejar de vivir solo desde eso.\n\n"
        "📅 *Presencial* · dom *6 sep 2026* · 9:00–18:00 · Zapopan\n"
        "💻 *Online* · desde *8 sep* · 5 sem · mar/jue 19:00–20:30\n\n"
        "💰 Preventa: presencial *$1,000* · online *$900*\n"
        "(Regular $1,200 / $1,000 · dúo y grupos con descuento)\n"
        "Apartas con *50%* · liquidar antes del *4 sep*\n\n"
        + (f"Más detalle: {url}\n\n" if url else "")
        + "¿Presencial u online? Elige abajo 💙"
    )


def _formatear_taller(t: dict) -> str:
    # Sin ficha “marketing” especial: mismo formato limpio que el resto
    nombre = t.get("nombre_corto_web") or t.get("nombre") or "Taller"
    lineas = [f"¡Claro! Te comparto la info de *{nombre}* ✨", ""]
    if t.get("nombre") and t.get("nombre") != nombre:
        lineas.append(f"• Nombre completo: *{t['nombre']}*")
    if t.get("terapeuta"):
        lineas.append(f"• Facilita: *{t['terapeuta']}*")
    if t.get("descripcion_web"):
        lineas.append(f"• De qué va: {t['descripcion_web']}")
    if t.get("libro_mes"):
        autor = t.get("autor_libro") or ""
        lineas.append(
            f"• Libro del mes: *{t['libro_mes']}*" + (f" ({autor})" if autor else "")
        )
    if t.get("fechas"):
        lineas.append(f"• Fechas: {t['fechas']}")
    if t.get("horario"):
        lineas.append(f"• Horario: {t['horario']}")
    if t.get("modalidad"):
        lineas.append(f"• Modalidad: {t['modalidad']}")
    if t.get("precio"):
        lineas.append(f"• Precio: *{t['precio']}*")
    if t.get("cupo"):
        lineas.append(f"• Cupo / formato: {t['cupo']}")
    if t.get("inscripcion"):
        lineas.append(f"• Inscripción: {t['inscripcion']}")
    if t.get("temario"):
        lineas.append(f"• Temario / enfoque: {t['temario']}")
    url = t.get("url_web") or PAGINAS_SITIO.get("talleres", "")
    if url:
        lineas.append(f"• Más detalle: {url}")
    lineas += ["", "Si quieres, después te oriento según lo que buscas 💙"]
    return "\n".join(lineas)


HERIDAS_IMAGE_URL = (
    f"{config.CLINICA_WEB_URL.rstrip('/')}/taller-heridas/hero.jpg"
)


def enviar_ficha_heridas_whatsapp(telefono: str, taller: dict | None = None) -> str:
    """
    Ficha con imagen+botones. DESACTIVADA por defecto: molestaba en saludos
    y saturaba el chat. Solo si ENABLE_FICHA_HERIDAS_WA=1.
    """
    import os

    from whatsapp import enviar_mensaje_whatsapp

    t = taller
    if not t:
        for item in obtener_talleres_vigentes():
            if item.get("id_web") == "sanando-heridas":
                t = item
                break
    texto = _formatear_taller_heridas(t or {})

    if os.getenv("ENABLE_FICHA_HERIDAS_WA", "0").strip().lower() not in (
        "1",
        "true",
        "yes",
        "si",
        "sí",
    ):
        enviar_mensaje_whatsapp(telefono, texto)
        return texto

    from whatsapp import enviar_botones_respuesta, enviar_imagen_por_url

    try:
        enviar_imagen_por_url(
            telefono,
            HERIDAS_IMAGE_URL,
            caption="Sanando tus heridas del pasado · Inpulso 43",
        )
        time.sleep(0.3)
    except Exception:
        pass

    cuerpo = texto
    if len(cuerpo) > 1024:
        cuerpo = cuerpo[:1021] + "..."
    enviar_botones_respuesta(
        telefono,
        cuerpo,
        [
            ("heridas_presencial", "Presencial"),
            ("heridas_online", "Online"),
            ("heridas_apartar", "Apartar lugar"),
        ],
    )
    return texto


def enviar_respuesta_catalogo_whatsapp(telefono: str, contenido: Any) -> str | None:
    """Catálogo por WhatsApp. Charla/saludos → None (sigue Gemini). Sin ficha rica."""
    from whatsapp import enviar_mensaje_whatsapp

    mensaje = _solo_mensaje_paciente(extraer_texto_usuario(contenido))
    if not mensaje or _es_charla_casual(mensaje):
        return None

    texto = intentar_respuesta_catalogo(contenido)
    if not texto:
        return None
    # Nunca imagen/botones en el flujo automático (solo texto)
    if texto.lstrip().startswith("✨ *Sanando tus heridas del pasado*"):
        if not _pide_taller_heridas(mensaje):
            return None
    enviar_mensaje_whatsapp(telefono, texto)
    return texto


def respuesta_boton_heridas(button_id: str) -> str | None:
    """Respuesta corta al pulsar botón (sin repetir toda la ficha)."""
    bid = (button_id or "").strip().lower()
    if bid == "heridas_presencial":
        return (
            "Perfecto, *presencial* 🌿\n\n"
            "Para apartar tu lugar dime tu *nombre completo* "
            "y te indico el anticipo del *50%* (liquidar antes del *4 sep*). "
            "¿Te anoto?"
        )
    if bid == "heridas_online":
        return (
            "Genial, *online* 💻\n\n"
            "Para reservar dime tu *nombre completo* "
            "y te indico el anticipo del *50%* (liquidar antes del *4 sep*). "
            "¿Te anoto?"
        )
    if bid == "heridas_apartar":
        return (
            "¡Claro! 🙌 Dime solo:\n"
            "1) *Presencial* u *online*\n"
            "2) Tu *nombre completo*\n\n"
            "Con eso te oriento para el anticipo."
        )
    return None


def _respuesta_listado_talleres() -> str:
    lineas = [
        "Estos son los *talleres y recursos* vigentes de Inpulso 43 ✨",
        "",
    ]
    for t in obtener_talleres_vigentes():
        nombre = t.get("nombre_corto_web") or t.get("nombre")
        precio = t.get("precio") or "Consultar"
        cuando = " · ".join(
            x for x in [t.get("fechas"), t.get("horario")] if x
        ) or "Fechas por confirmar"
        lineas.append(
            f"• *{nombre}* — {t.get('terapeuta', '')}\n"
            f"  {cuando} · {t.get('modalidad', '')} · *{precio}*"
        )
    lineas += [
        "",
        f"Catálogo completo: {PAGINAS_SITIO.get('talleres', config.CLINICA_WEB_URL)}",
        "Si me dices cuál te interesa, te doy el detalle completo 💙",
    ]
    return "\n".join(lineas)


def _bloque_precios_especialista(clave: str, data: dict) -> list[str]:
    etiqueta = _ETIQUETAS_PRECIO.get(clave, clave.title())
    lineas = [f"*{etiqueta}*"]
    if "individual" in data:
        lineas.append(f"  • Individual: *{data['individual']}* MXN")
    if "pareja" in data:
        lineas.append(f"  • Pareja: *{data['pareja']}* MXN")
    if "familiar" in data:
        lineas.append(f"  • Familiar: *{data['familiar']}* MXN")
    if "general" in data:
        lineas.append(f"  • Consulta: *{data['general']}* MXN")
    if "consulta" in data and "general" not in data:
        lineas.append(f"  • Consulta: *{data['consulta']}*")
    if data.get("modalidad"):
        lineas.append(f"  • Modalidad: {data['modalidad']}")
    return lineas


def _respuesta_precios(mensaje: str) -> str | None:
    n = _norm(mensaje)
    pide_precio = bool(
        re.search(r"precio|precios|cuesta|cuanto|costo|costos|tarif", n)
    )
    pide_todo = bool(
        re.search(r"\b(todos|todas|completo|lista|catalogo|servicios)\b", n)
    ) or (pide_precio and not any(
        alias in n for aliases in _NOMBRES_PRECIO.values() for alias in aliases
    ))

    data = _cargar_precios()
    if not data:
        return None

    # Especialista concreto
    clave_hit = None
    for clave, aliases in _NOMBRES_PRECIO.items():
        if any(_norm(a) in n for a in aliases):
            clave_hit = clave
            break

    if clave_hit and clave_hit in data and (
        pide_precio or "sesion" in n or "consulta" in n or "cuanto" in n
    ):
        bloque = _bloque_precios_especialista(clave_hit, data[clave_hit])
        mentoras = data.get("mentoras", {}).get("nota_importante", "")
        lineas = ["Con gusto te comparto los *precios* ✨", ""] + bloque
        if mentoras and "mentora" in n:
            lineas += ["", f"Nota: {mentoras}"]
        lineas += [
            "",
            "Modalidad de consultas: presencial en Inpulso 43 y en línea "
            "(las *mentoras* son únicamente en línea).",
            "Horario para agendar citas: lunes a viernes, 7:00 am a 7:00 pm.",
        ]
        return "\n".join(lineas)

    if not (pide_precio or pide_todo or re.search(r"cuanto (cuesta|salen)|precios?", n)):
        # "cuáles son sus precios" etc.
        if not re.search(r"precio|cuesta|costo|tarif", n):
            return None

    lineas = [
        "Estos son los *precios de consulta* en Inpulso 43 ✨",
        "",
    ]
    for clave in ("sara", "juan", "patricia", "ivan", "nutricionista", "medicina"):
        if clave in data and isinstance(data[clave], dict):
            lineas.extend(_bloque_precios_especialista(clave, data[clave]))
            lineas.append("")
    mentoras = data.get("mentoras", {}).get("nota_importante")
    if mentoras:
        lineas.append(f"• Mentoras: {mentoras}")
    lineas += [
        "",
        "• Talleres/recursos: varían (hay gratuitos como el club de lectura). "
        "Pregúntame por el que te interese.",
        "• Horario de citas: lunes a viernes, 7:00 am – 7:00 pm.",
        f"• Más info: {PAGINAS_SITIO.get('talleres', config.CLINICA_WEB_URL)}",
    ]
    return "\n".join(lineas)


def _respuesta_equipo(mensaje: str) -> str | None:
    n = _norm(mensaje)
    if not re.search(
        r"equipo|terapeutas|quienes (atienden|trabajan)|especialistas|"
        r"psicologos|nutriolog|quien es sara|quien es juan|staff",
        n,
    ):
        # Nombre concreto de alguien del equipo
        hit = None
        for persona in EQUIPO_WEB:
            if _norm(persona["nombre"].split()[0]) in n and re.search(
                r"quien|info|sobre|que hace|especialidad", n
            ):
                hit = persona
                break
        if not hit:
            return None
        return (
            f"*{hit['nombre']}* — {hit['rol']} ✨\n"
            f"• Especialidades: {hit['especialidades']}\n"
            f"• Modalidad: {hit['modalidad']}\n\n"
            "Si quieres, te comparto precios o te oriento para agendar 💙"
        )

    lineas = ["Este es el *equipo* de Inpulso 43 ✨", ""]
    for p in EQUIPO_WEB:
        lineas.append(
            f"• *{p['nombre']}* ({p['rol']}) — {p['especialidades']} "
            f"[{p['modalidad']}]"
        )
    lineas += [
        "",
        f"Más sobre el equipo: {PAGINAS_SITIO.get('nosotros', config.CLINICA_WEB_URL)}",
    ]
    return "\n".join(lineas)


def _respuesta_contacto(mensaje: str) -> str | None:
    n = _norm(mensaje)
    if not re.search(
        r"donde|ubicacion|direccion|como llegar|mapa|contacto|telefono|"
        r"whatsapp|estacionamiento|horario (de )?atencion|abren|cierran",
        n,
    ):
        return None
    tels = ", ".join(CONTACTO_WEB.get("telefonos") or [])
    lineas = [
        "Con gusto, aquí tienes nuestros datos de *contacto* 📍",
        "",
        f"• Dirección: {CONTACTO_WEB.get('direccion') or config.CLINICA_DIRECCION}",
        f"• Mapa: {config.CLINICA_MAPS_URL}",
        f"• Teléfonos: {tels}" if tels else "",
    ]
    if config.WHATSAPP_PACIENTES_URL:
        lineas.append(f"• WhatsApp pacientes: {config.WHATSAPP_PACIENTES_URL}")
    lineas += [
        "• Estacionamiento: sí hay, *un solo cajón* (sujeto a disponibilidad).",
        "• Citas: lunes a viernes, 7:00 am a 7:00 pm (presencial y en línea).",
        "• Alessia (este chat) responde 24 h para información y dudas.",
        f"• Sitio: {config.CLINICA_WEB_URL}",
    ]
    return "\n".join(x for x in lineas if x)


def _respuesta_pagos(mensaje: str) -> str | None:
    n = _norm(mensaje)
    if not re.search(
        r"pago|pagar|transferencia|clabe|banorte|banamex|efectivo|tarjeta|factura",
        n,
    ):
        return None
    # No interceptar si es claramente comprobante/tramite de pago en curso
    if re.search(r"comprobante|ya pague|envie el pago|confirmar pago", n):
        return None
    banorte = config.CUENTAS_OFICIALES.get("BANORTE", {})
    banamex = config.CUENTAS_OFICIALES.get("BANAMEX", {})
    lineas = [
        "Formas de *pago* en Inpulso 43 💳",
        "",
        "• Efectivo en recepción",
        "• Tarjeta (débito/crédito) en recepción",
        "• Transferencia *sin factura* — BANORTE:",
        f"  Tarjeta {banorte.get('tarjeta', '—')} · CLABE {banorte.get('clabe', '—')} "
        f"a nombre de {banorte.get('titular', '—')}",
        "• Transferencia *con factura* — BANAMEX:",
        f"  Cuenta {banamex.get('cuenta', '—')} · CLABE {banamex.get('clabe', '—')} "
        f"a nombre de {banamex.get('titular', '—')}",
        "",
        "En el concepto pon tu *nombre completo*. "
        "Las citas *en línea* se pagan completas al confirmar (a más tardar 24 h antes).",
        "Si cancelas con menos de 24 h, aplica penalización del 50%.",
    ]
    return "\n".join(lineas)


def _respuesta_faq_clinica(mensaje: str) -> str | None:
    n = _norm(mensaje)
    if re.search(r"que es inpulso|quienes son|en que consiste|modelo 360|como funciona", n):
        lineas = [
            f"*{config.CLINICA_WEB_URL.replace('https://', '')}* — bienestar para mente y cuerpo ✨",
            "",
            MENSAJE_BASE_WEB,
            "",
            "*Especialidades:*",
        ]
        for k, v in ESPECIALIDADES_INPULSO.items():
            lineas.append(f"• *{k.title()}*: {v}")
        lineas += ["", "*Cómo acompañamos:*"]
        for paso in METODO_WEB:
            lineas.append(f"• {paso}")
        lineas += ["", "*Áreas:*"]
        for area in AREAS_ACOMPANAMIENTO_WEB:
            lineas.append(f"• {area}")
        return "\n".join(lineas)

    if re.search(r"seguro|aseguradora|reembolso", n):
        return (
            "Inpulso 43 *no trabaja directo con aseguradoras*, pero emite factura "
            "para que puedas solicitar reembolso si tu póliza lo permite 💙"
        )

    if re.search(r"duracion|cuanto dura|minutos|sesion dura", n):
        return (
            "Las sesiones individuales suelen durar entre *50 y 60 minutos* ✨ "
            "Si quieres, te oriento según el tipo de consulta."
        )

    if re.search(r"\bfaq\b|preguntas frecuentes|dudas generales", n):
        lineas = ["Algunas *respuestas frecuentes* ✨", ""]
        for item in FAQ_WEB:
            lineas.append(f"• {item}")
        return "\n".join(lineas)
    return None


def _respuesta_conocimiento(mensaje: str) -> str | None:
    try:
        import storage

        hits = storage.buscar_conocimiento_clinica(mensaje, limite=3)
    except Exception:
        return None
    if not hits:
        return None
    # Solo si hay match fuerte (tema/palabras muy alineadas)
    top = hits[0]
    tokens = [
        t
        for t in re.findall(r"[a-záéíóúñü0-9]{4,}", _norm(mensaje))
        if t not in {"para", "sobre", "como", "cuando", "donde", "cuesta", "precio"}
    ]
    blob = _norm(f"{top.get('tema', '')} {top.get('palabras_clave', '')}")
    score = sum(1 for t in tokens if t in blob or t in _norm(top.get("contenido", "")))
    if score < 2 and _norm(top.get("tema", "")) not in _norm(mensaje):
        return None
    lineas = [
        f"Te comparto lo que tenemos registrado sobre *{top['tema']}* ✨",
        "",
        (top.get("contenido") or "").strip(),
    ]
    if len(hits) > 1:
        lineas += ["", "También relacionado:"]
        for h in hits[1:]:
            lineas.append(f"• *{h['tema']}*: {(h.get('contenido') or '')[:160]}")
    return "\n".join(lineas)


def _respuesta_taller(mensaje: str) -> str | None:
    tid = id_web_desde_texto(mensaje)
    n = mensaje.lower()
    if not tid:
        if "club" in n and "lectura" in n:
            tid = "sara-club"
        elif "mente" in _norm(mensaje) and "capitulo" in _norm(mensaje):
            tid = "sara-club"
    if not tid:
        return None
    # Heridas: nunca por coincidencia débil; solo si lo pidieron
    if tid == "sanando-heridas" and not _pide_taller_heridas(mensaje):
        return None
    for t in obtener_talleres_vigentes(forzar_web=False):
        if t.get("id_web") == tid:
            return _formatear_taller(t)
    return None


def _pide_listado_talleres(mensaje: str) -> bool:
    n = _norm(mensaje)
    return bool(
        re.search(
            r"(que|cuales|lista|catalogo).*(taller|recurso)|"
            r"(taller|talleres).*(tienen|ofrecen|hay|disponibles)|"
            r"\btalleres\b\s*\?|informacion de (los )?talleres",
            n,
        )
    )


def intentar_respuesta_catalogo(contenido: Any) -> str | None:
    """Respuesta factual inmediata si la pregunta es de información clara."""
    crudo = extraer_texto_usuario(contenido)
    mensaje = _solo_mensaje_paciente(crudo)
    if not mensaje or _es_charla_casual(mensaje):
        return None
    if not _parece_pregunta_info(mensaje):
        return None

    # Orden: lo más específico primero
    for builder in (
        lambda: _respuesta_taller(mensaje),
        lambda: _respuesta_precios(mensaje),
        lambda: _respuesta_listado_talleres() if _pide_listado_talleres(mensaje) else None,
        lambda: _respuesta_equipo(mensaje),
        lambda: _respuesta_contacto(mensaje),
        lambda: _respuesta_pagos(mensaje),
        lambda: _respuesta_faq_clinica(mensaje),
        lambda: _respuesta_conocimiento(mensaje),
    ):
        out = builder()
        if out:
            return out
    return None


def bloque_hechos_forzado(contenido: Any) -> str:
    mensaje = _solo_mensaje_paciente(extraer_texto_usuario(contenido))
    if _es_charla_casual(mensaje):
        return (
            "[Sistema: El paciente solo saludó o hace charla. "
            "Responde en 1-2 frases cálidas. "
            "PROHIBIDO mencionar talleres, heridas del pasado, Sanando, "
            "precios de talleres, presencial/online o botones. "
            "Pregunta en qué le puedes ayudar.]\n"
        )
    hechos = intentar_respuesta_catalogo(contenido)
    if hechos:
        return (
            "[Sistema: RESPUESTA OBLIGATORIA — no digas que vas a revisar. "
            "Reformula con calidez usando EXACTAMENTE estos hechos; no inventes:]\n"
            f"{hechos}\n"
        )
    # NO soltar catálogo de talleres si no lo pidieron
    return (
        "[Sistema: Responde con calidez. Si no tienes el dato, pregunta qué necesita. "
        "PROHIBIDO inventar y PROHIBIDO soltar el taller de heridas u otros talleres "
        "si el paciente no los mencionó.]\n"
    )


def asegurar_respuesta_util(
    contenido: Any,
    texto_modelo: str,
    *,
    regenerar,
) -> str:
    mensaje = _solo_mensaje_paciente(extraer_texto_usuario(contenido))
    texto = (texto_modelo or "").strip()
    # En charla, no regenerar con hechos de catálogo/talleres
    if _es_charla_casual(mensaje):
        if texto and not es_respuesta_relleno(texto):
            # Si el modelo soltó el taller en un saludo, forzar reescritura
            bajo = texto.lower()
            if "heridas" in bajo or "sanando" in bajo:
                try:
                    segundo = (
                        regenerar(
                            bloque_hechos_forzado(contenido)
                            + extraer_texto_usuario(contenido)
                        )
                        or ""
                    ).strip()
                except Exception:
                    segundo = ""
                if segundo and "heridas" not in segundo.lower():
                    return segundo
                return (
                    "¡Hola! Qué gusto saludarte 😊 ¿En qué te puedo ayudar hoy?"
                )
            return texto
        try:
            segundo = (
                regenerar(
                    bloque_hechos_forzado(contenido) + extraer_texto_usuario(contenido)
                )
                or ""
            ).strip()
        except Exception:
            segundo = ""
        if segundo and "heridas" not in segundo.lower() and "sanando" not in segundo.lower():
            return segundo
        return "¡Hola! Qué gusto saludarte 😊 ¿En qué te puedo ayudar hoy?"

    if texto and not es_respuesta_relleno(texto):
        return texto

    fijo = intentar_respuesta_catalogo(contenido)
    if fijo and (
        "sanando tus heridas" in fijo.lower() or "elige abajo" in fijo.lower()
    ):
        # Nunca inyectar ficha taller como “rescate”
        fijo = None
    if fijo:
        return fijo

    try:
        segundo = (
            regenerar(bloque_hechos_forzado(contenido) + extraer_texto_usuario(contenido))
            or ""
        ).strip()
    except Exception:
        segundo = ""
    if segundo and not es_respuesta_relleno(segundo):
        return segundo
    return fijo or texto or ""
