"""Detección de solicitud de hablar con humano / recepción."""
from __future__ import annotations

import re
import unicodedata


def _sin_acentos(texto: str) -> str:
    nfd = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def es_solicitud_humano(texto: str) -> bool:
    """True si el paciente pide hablar con persona/recepción (no solo info)."""
    limpio = _sin_acentos((texto or "").strip().lower())
    limpio = re.sub(r"[^\w\s]", " ", limpio)
    limpio = re.sub(r"\s+", " ", limpio).strip()

    if not limpio:
        return False

    if limpio in {
        "hablar con persona",
        "hablar con una persona",
        "hablar con alguien",
        "hablar con recepcion",
        "quiero hablar con persona",
        "quiero hablar con una persona",
        "quiero hablar con alguien",
        "necesito hablar con alguien",
        "necesito una persona",
        "pasar con recepcion",
        "pasar a recepcion",
        "agente humano",
        "asesor humano",
    }:
        return True

    patrones = (
        r"\bhablar con (una )?persona\b",
        r"\bhablar con (un )?humano\b",
        r"\bhablar con alguien\b",
        r"\bhablar con recepcion\b",
        r"\bquiero (hablar con |pasar (a |con )?|atencion de )?recepcion\b",
        r"\bnecesito (hablar con )?(una )?persona\b",
        r"\bpasame (con |a )?(una )?persona\b",
        r"\btransferir(me)? (a |con )?(humano|persona|recepcion)\b",
        r"\bno (quiero|deseo) (hablar con )?(un )?(bot|ia|asistente)\b",
        r"\b(atencion|asesor) humana?\b",
    )
    return any(re.search(p, limpio) for p in patrones)


def mensaje_confirmacion_escalacion(aviso_enviado: bool, recepcion_configurada: bool) -> str:
    if aviso_enviado:
        return (
            "Entendido 😊 Ya avisé al equipo de recepción. "
            "Una persona te contactará pronto por este mismo chat."
        )
    if not recepcion_configurada:
        return (
            "Claro, te conecto con el equipo 💙 "
            "Por ahora puedes marcar a *+52 33 1469 9772* o *+52 331 230 2221* "
            "y con gusto te atienden. También puedes escribir de nuevo *HABLAR CON PERSONA*."
        )
    return (
        "Registré tu solicitud 💙 El equipo la verá enseguida. "
        "Si es urgente, marca *+52 33 1469 9772* o *+52 331 230 2221*."
    )
