"""Capa de respuestas fiables — cobertura amplia de información."""
from respuesta_fiable import (
    es_respuesta_relleno,
    intentar_respuesta_catalogo,
    asegurar_respuesta_util,
)


def test_club_lectura_sara():
    out = intentar_respuesta_catalogo(
        "podrías darme información sobre el club de lectura de sara?"
    )
    assert out and "Mente en Capítulos" in out and "Sara Rosales" in out
    assert "Gratuito" in out or "gratis" in out.lower()


def test_heridas():
    out = intentar_respuesta_catalogo("¿qué es el taller de heridas del pasado?")
    assert out and "Sanando" in out
    assert "$1,000" in out or "$1000" in out or "1,000" in out
    assert "50%" in out or "sep" in out.lower()
    # Formato normal de taller (no ficha marketing con "Elige abajo")
    assert "Elige abajo" not in out


def test_saludo_no_dispara_catalogo():
    from respuesta_fiable import _es_solo_saludo, _es_charla_casual

    assert _es_solo_saludo("Hola buenas tardes")
    assert _es_solo_saludo("hola")
    assert _es_charla_casual("Cómo estás?")
    assert _es_charla_casual("Como estas")
    assert not _es_solo_saludo("hola, info del taller de heridas")
    assert intentar_respuesta_catalogo("Hola buenas tardes") is None
    assert intentar_respuesta_catalogo("Cómo estás?") is None
    assert intentar_respuesta_catalogo(
        "[Sistema: Mensaje recibido el X] Hola buenas tardes"
    ) is None
    # Sí responde si piden el taller
    assert intentar_respuesta_catalogo(
        "hola, info del taller de heridas del pasado"
    )


def test_boton_heridas_presencial():
    from respuesta_fiable import respuesta_boton_heridas

    out = respuesta_boton_heridas("heridas_presencial")
    assert out and "presencial" in out.lower()
    assert "nombre completo" in out.lower()
    # No debe repetir toda la ficha de precios/fechas
    assert "$1,000" not in out and "6 sep" not in out


def test_listado_talleres():
    out = intentar_respuesta_catalogo("¿qué talleres tienen?")
    assert out
    assert "Mente en Capítulos" in out
    assert "Sanando" in out
    assert "Alianza 360" in out


def test_precios_todos():
    out = intentar_respuesta_catalogo("¿cuáles son todos los precios?")
    assert out
    assert "$800" in out
    assert "$1000" in out  # Juan
    assert "Nutrición" in out or "nutrición" in out.lower() or "Gabriela" in out


def test_precio_sara():
    out = intentar_respuesta_catalogo("¿cuánto cuesta la sesión individual con Sara?")
    assert out and "Sara" in out and "$800" in out and "$900" in out


def test_precio_juan():
    out = intentar_respuesta_catalogo("precios de juan rosales")
    assert out and "$1000" in out


def test_precio_nutricion():
    out = intentar_respuesta_catalogo("cuánto cuesta nutrición con gabriela")
    assert out and "$450" in out


def test_equipo():
    out = intentar_respuesta_catalogo("¿quiénes son los terapeutas del equipo?")
    assert out and "Sara Rosales" in out and "Gabriela Sánchez" in out


def test_contacto_ubicacion():
    out = intentar_respuesta_catalogo("¿dónde están ubicados?")
    assert out and "Hidalgo" in out and "Zapopan" in out


def test_pagos():
    out = intentar_respuesta_catalogo("¿cómo puedo pagar por transferencia?")
    assert out and "BANORTE" in out and "CLABE" in out


def test_faq_seguros():
    out = intentar_respuesta_catalogo("¿trabajan con seguros o aseguradoras?")
    assert out and "aseguradoras" in out.lower()


def test_que_es_inpulso():
    out = intentar_respuesta_catalogo("¿qué es Inpulso 43 y cómo funciona?")
    assert out and "psicología" in out.lower()


def test_no_intercepta_agendar_puro():
    assert intentar_respuesta_catalogo("quiero agendar cita con sara mañana") is None


def test_relleno():
    assert es_respuesta_relleno("Permíteme un momento para revisar ✨")
    assert not es_respuesta_relleno("La individual con Sara es *$800* MXN.")


def test_asegurar_catalogo_si_relleno():
    fijo = asegurar_respuesta_util(
        "info del club de lectura",
        "Permíteme un momento para revisar nuestros recursos ✨",
        regenerar=lambda _m: "otra vez déjame revisar",
    )
    assert "Mente en Capítulos" in fijo
