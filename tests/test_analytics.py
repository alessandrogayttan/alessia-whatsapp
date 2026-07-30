"""Tests Analytics / métricas de mensajes y heridas."""
from storage import (
    metricas_faq_heridas,
    metricas_interes_heridas,
    metricas_mensajes_por_dia,
    metricas_resumen_historico,
)


def test_metricas_mensajes_por_dia_rellena_dias(db_temp):
    import storage

    storage.guardar_mensaje_conversacion(
        "wa:523311111111", "whatsapp", "user", "hola quiero el taller de heridas"
    )
    dias = metricas_mensajes_por_dia(7)
    assert len(dias) >= 7
    assert sum(d["mensajes"] for d in dias) >= 1
    assert sum(d["menciones_heridas"] for d in dias) >= 1


def test_metricas_faq_heridas(db_temp):
    import storage

    storage.registrar_pregunta_frecuente(
        "cuanto cuesta el taller de heridas", "523311111111"
    )
    hits = metricas_faq_heridas()
    assert hits
    assert "herida" in hits[0]["pregunta"]


def test_mensajes_recientes_incluye_telefono(db_temp):
    import storage

    storage.guardar_mensaje_conversacion(
        "wa:523312345678", "whatsapp", "user", "hola quiero info del taller"
    )
    rows = storage.mensajes_recientes_pacientes(10)
    assert rows
    assert rows[0]["telefono"] == "523312345678"


def test_faq_incluye_whatsapp(db_temp):
    import storage

    storage.registrar_pregunta_frecuente("precio sara", "523399999999")
    top = storage.top_preguntas_frecuentes(5)
    assert top[0].get("ejemplo_telefono") == "523399999999"
