"""Capa de respuestas fiables: hechos de catálogo sin depender solo de Gemini.

Objetivo: preguntas claras sobre talleres/recursos conocidos nunca se queden
en "déjame revisar…". WhatsApp y web usan la misma lógica.
"""
from __future__ import annotations

import re
from typing import Any

from catalogo_web import id_web_desde_texto, obtener_talleres_vigentes
from conocimiento import parece_consulta_informativa

_RELLENO = re.compile(
    r"("
    r"dejame revisar|déjame revisar|permiteme|permíteme un momento|"
    r"un momentito|dame un momento|voy a buscar|busco (la )?informaci[oó]n|"
    r"reviso (nuestros )?recursos|estoy buscando|te confirmo en un momento|"
    r"ya lo estoy revisando|d[eé]jame checar|déjame checar"
    r")",
    re.I,
)

_TRAMITE = re.compile(
    r"\b("
    r"agendar|agenda|cita|inscribir|inscripci[oó]n|pagar|pago|comprobante|"
    r"cancelar|reagendar|factura|cfdi|hablar con persona|emergencia"
    r")\b",
    re.I,
)

_INFO = re.compile(
    r"("
    r"\?|¿|informaci[oó]n|info|cu[aá]nto|cuesta|precio|horario|cu[aá]ndo|"
    r"d[oó]nde|qu[eé] es|de qu[eé]|sobre (el|la|los|las)|taller|club|"
    r"lectura|temario|cupo|modalidad|gratis|gratuito"
    r")",
    re.I,
)


def extraer_texto_usuario(contenido: Any) -> str:
    """Obtiene el texto del paciente desde str o partes multimodales."""
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
    """Quita prefijos [Sistema: ...] para matching."""
    lineas = []
    for linea in (texto or "").splitlines():
        if linea.strip().startswith("[Sistema:"):
            continue
        lineas.append(linea)
    return "\n".join(lineas).strip() or (texto or "").strip()


def es_respuesta_relleno(texto: str) -> bool:
    """True si el modelo pospuso la respuesta sin dar hechos útiles."""
    t = (texto or "").strip()
    if not t:
        return True
    if not _RELLENO.search(t):
        return False
    # Si además trae datos concretos (precio, horario, nombre de taller), no es solo relleno
    hechos = re.search(
        r"("
        r"\$\s*\d|mxn|gratis|gratuito|viernes|lunes|martes|mi[eé]rcoles|jueves|"
        r"s[aá]bado|domingo|\d{1,2}:\d{2}|\d{1,2}\s*(am|pm)|mente en cap[ií]tulos|"
        r"sanando|alianza 360|clabe|banorte|zapopan|hidalgo"
        r")",
        t,
        re.I,
    )
    return hechos is None


def _formatear_taller(t: dict) -> str:
    nombre = t.get("nombre_corto_web") or t.get("nombre") or "Taller"
    lineas = [
        f"¡Claro! Te comparto la info de *{nombre}* ✨",
        "",
    ]
    if t.get("nombre") and t.get("nombre") != nombre:
        lineas.append(f"• Nombre completo: *{t['nombre']}*")
    if t.get("terapeuta"):
        lineas.append(f"• Facilita: *{t['terapeuta']}*")
    if t.get("descripcion_web"):
        lineas.append(f"• De qué va: {t['descripcion_web']}")
    if t.get("libro_mes"):
        autor = t.get("autor_libro") or ""
        libro = t["libro_mes"]
        lineas.append(
            f"• Libro del mes: *{libro}*" + (f" ({autor})" if autor else "")
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
    url = t.get("url_web") or ""
    if url:
        lineas.append(f"• Más detalle: {url}")
    lineas.append("")
    lineas.append(
        "Si quieres, después te ayudo a registrar tu interés o a orientarte "
        "según lo que buscas 💙"
    )
    return "\n".join(lineas)


def _parece_pregunta_info(texto: str) -> bool:
    if _TRAMITE.search(texto):
        return False
    if parece_consulta_informativa(texto):
        return True
    return bool(_INFO.search(texto))


def intentar_respuesta_catalogo(contenido: Any) -> str | None:
    """
    Si la pregunta es claramente sobre un taller/recurso del catálogo,
    responde con hechos sin pasar por Gemini.
    """
    crudo = extraer_texto_usuario(contenido)
    mensaje = _solo_mensaje_paciente(crudo)
    if not mensaje or not _parece_pregunta_info(mensaje):
        return None

    tid = id_web_desde_texto(mensaje)
    if not tid:
        # Refuerzo: "club de lectura" + sara
        n = mensaje.lower()
        if "club" in n and "lectura" in n and "sara" in n:
            tid = "sara-club"
        elif "mente" in n and "capitulo" in n.replace("í", "i"):
            tid = "sara-club"
    if not tid:
        return None

    for t in obtener_talleres_vigentes():
        if t.get("id_web") == tid:
            return _formatear_taller(t)
    return None


def bloque_hechos_forzado(contenido: Any) -> str:
    """Texto de sistema para reintento cuando Gemini respondió con relleno."""
    hechos = intentar_respuesta_catalogo(contenido)
    if hechos:
        return (
            "[Sistema: RESPUESTA OBLIGATORIA — no digas que vas a revisar. "
            "Reformula con calidez usando EXACTAMENTE estos hechos; no inventes:]\n"
            f"{hechos}\n"
        )
    return (
        "[Sistema: Tu mensaje anterior fue solo relleno. "
        "Responde YA con datos concretos usando WEB VIVA / herramientas. "
        "PROHIBIDO decir déjame revisar o un momentito.]\n"
    )


def asegurar_respuesta_util(
    contenido: Any,
    texto_modelo: str,
    *,
    regenerar,
) -> str:
    """
    Si el modelo mandó relleno, regenera una vez con hechos forzados.
    `regenerar` recibe un string (instrucción + mensaje) y debe devolver texto.
    """
    texto = (texto_modelo or "").strip()
    if texto and not es_respuesta_relleno(texto):
        return texto

    fijo = intentar_respuesta_catalogo(contenido)
    if fijo:
        return fijo

    try:
        segundo = (regenerar(bloque_hechos_forzado(contenido) + extraer_texto_usuario(contenido)) or "").strip()
    except Exception:
        segundo = ""
    if segundo and not es_respuesta_relleno(segundo):
        return segundo
    return fijo or texto or ""
