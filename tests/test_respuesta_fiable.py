"""Capa de respuestas fiables (catálogo + anti-relleno)."""
from respuesta_fiable import (
    es_respuesta_relleno,
    intentar_respuesta_catalogo,
    asegurar_respuesta_util,
)


def test_club_lectura_sara_respuesta_inmediata():
    out = intentar_respuesta_catalogo(
        "podrías darme información sobre el club de lectura de sara?"
    )
    assert out
    assert "Mente en Capítulos" in out
    assert "Sara Rosales" in out
    assert "6:00 PM" in out or "6:00" in out
    assert "Gratuito" in out or "gratis" in out.lower()
    assert "déjame revisar" not in out.lower()


def test_heridas_respuesta_inmediata():
    out = intentar_respuesta_catalogo("¿qué es el taller de heridas del pasado?")
    assert out
    assert "Sanando" in out
    assert "HISTORIA" in out or "lista de espera" in out.lower()


def test_no_intercepta_agendar():
    assert (
        intentar_respuesta_catalogo("quiero agendar el club de lectura de sara") is None
    )


def test_detecta_relleno_sin_hechos():
    assert es_respuesta_relleno(
        "¡Claro Alessandro! Con gusto busco información. Permíteme un momento ✨"
    )
    assert not es_respuesta_relleno(
        "¡Claro! *Mente en Capítulos* es gratuito los viernes a las 6:00 PM."
    )


def test_asegurar_usa_catalogo_si_relleno():
    fijo = asegurar_respuesta_util(
        "info del club de lectura",
        "Permíteme un momento para revisar nuestros recursos ✨",
        regenerar=lambda _m: "otra vez déjame revisar",
    )
    assert "Mente en Capítulos" in fijo
