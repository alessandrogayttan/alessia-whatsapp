"""Tests persistencia, RAG y unificación de conversación."""
import storage
from conversacion import (
    clave_conversacion_web,
    historial_para_gemini,
    registrar_turno,
    vincular_conversacion_web,
)
from inpulso_rag import _partir_chunks, buscar_conocimiento_inpulso, reindexar_sitio_inpulso


def test_guardar_y_cargar_historial(db_temp, monkeypatch):
    monkeypatch.setattr("config.ENABLE_CONVERSACION_PERSISTENTE", True)
    monkeypatch.setattr("conversacion.config.ENABLE_CONVERSACION_PERSISTENTE", True)
    clave = "5233999888777"
    registrar_turno(clave, "whatsapp", "Hola", "Hola, ¿en qué te ayudo?")
    msgs = storage.obtener_mensajes_conversacion(clave, limite=10)
    assert len(msgs) == 2
    historial = historial_para_gemini(clave)
    assert len(historial) == 2
    assert historial[0].role == "user"


def test_vincular_web_whatsapp(db_temp, monkeypatch):
    monkeypatch.setattr("config.ENABLE_CONVERSACION_PERSISTENTE", True)
    monkeypatch.setattr("conversacion.config.ENABLE_CONVERSACION_PERSISTENTE", True)
    sid = "550e8400-e29b-41d4-a716-446655440000"
    web_clave = clave_conversacion_web(sid, None)
    tel = "5233111222333"
    registrar_turno(web_clave, "web", "Pregunta web", "Respuesta web")
    vincular_conversacion_web(sid, tel)
    msgs = storage.obtener_mensajes_conversacion(tel, limite=10)
    assert len(msgs) == 2
    assert storage.obtener_mensajes_conversacion(web_clave, limite=10) == []


def test_rag_chunks_y_busqueda(db_temp, monkeypatch):
    monkeypatch.setattr("config.ENABLE_INPULSO_RAG", True)
    monkeypatch.setattr("inpulso_rag.config.ENABLE_INPULSO_RAG", True)
    chunks = _partir_chunks("Taller Sanando heridas del pasado con Sara Rosales en Inpulso 43")
    storage.limpiar_rag_indice()
    storage.insertar_chunks_rag([("web:talleres", "https://inpulso43.com/talleres.php", c) for c in chunks])
    out = buscar_conocimiento_inpulso("taller heridas Sara")
    assert "Sanando" in out or "heridas" in out


def test_reindexar_mock(db_temp, monkeypatch):
    monkeypatch.setattr("config.ENABLE_INPULSO_RAG", True)
    monkeypatch.setattr(
        "inpulso_rag._chunks_desde_pagina",
        lambda clave: [("web:" + clave, f"https://x/{clave}", "contenido de prueba inpulso")],
    )
    monkeypatch.setattr("inpulso_rag._extraer_pdfs_desde_html", lambda h, u: [])
    total = reindexar_sitio_inpulso(forzar=True)
    assert total >= 6
