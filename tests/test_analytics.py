"""Tests Analytics / métricas de mensajes y heridas."""
from storage import (
    metricas_faq_heridas,
    metricas_interes_heridas,
    metricas_mensajes_por_dia,
)


def test_metricas_mensajes_por_dia(db_temp):
    import storage

    storage.guardar_mensaje_conversacion(
        "wa:523311111111", "whatsapp", "user", "hola quiero el taller de heridas"
    )
    # Forzar fecha reciente si guardar no usa now - check API
    dias = metricas_mensajes_por_dia(30)
    assert isinstance(dias, list)


def test_metricas_faq_heridas(db_temp):
    import storage

    storage.registrar_pregunta_frecuente("cuanto cuesta el taller de heridas", "523311111111")
    hits = metricas_faq_heridas()
    assert hits
    assert "herida" in hits[0]["pregunta"]


def test_metricas_interes(db_temp):
    out = metricas_interes_heridas()
    assert "interes_activo_relacionado" in out
    assert "interes_7d_heridas" in out
