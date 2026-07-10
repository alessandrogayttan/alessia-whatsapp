"""Tests modo equipo interno — IA completa para staff."""
import os

import pytest


def test_instrucciones_equipo_identidad():
    from modo_equipo import _instrucciones_equipo

    texto = _instrucciones_equipo("Alessandro")
    assert "Alessandro Gaytán" in texto
    assert "Google DeepMind" in texto
    assert "PROHIBIDO decir que eres Gemini" in texto
    assert "Tu nombre es *Alessia*" in texto


def test_identificar_miembro_equipo_alessandro(monkeypatch):
    monkeypatch.setenv("ENABLE_MODO_EQUIPO", "1")
    monkeypatch.setenv("WHATSAPP_ALESSANDRO", "5233123456789")

    import importlib

    import config

    importlib.reload(config)

    assert config.identificar_miembro_equipo("5233123456789") == "Alessandro"
    assert config.identificar_miembro_equipo("52133123456789") == "Alessandro"
    assert config.identificar_miembro_equipo("5233999999999") is None


def test_identificar_miembro_equipo_desactivado(monkeypatch):
    monkeypatch.setenv("ENABLE_MODO_EQUIPO", "0")
    monkeypatch.setenv("WHATSAPP_ALESSANDRO", "5233123456789")

    import importlib

    import config

    importlib.reload(config)

    assert config.identificar_miembro_equipo("5233123456789") is None


def test_envolver_mensaje_equipo(monkeypatch):
    monkeypatch.setenv("ENABLE_MODO_EQUIPO", "1")
    monkeypatch.setenv("WHATSAPP_ALESSANDRO", "5233123456789")

    import importlib

    import config
    from modo_equipo import envolver_mensaje_equipo

    importlib.reload(config)

    resultado = envolver_mensaje_equipo("5233123456789", "Organiza este borrador")
    assert "MODO EQUIPO INTERNO" in resultado
    assert "Alessandro" in resultado
    assert "Organiza este borrador" in resultado


def test_procesar_mensaje_ia_rutea_equipo(monkeypatch):
    monkeypatch.setenv("ENABLE_MODO_EQUIPO", "1")
    monkeypatch.setenv("WHATSAPP_ALESSANDRO", "5233123456789")

    import importlib

    import chat
    import config

    importlib.reload(config)
    importlib.reload(chat)

    llamadas: list[tuple] = []

    def fake_procesar_equipo(tel, contenido):
        llamadas.append((tel, contenido))
        return "Respuesta equipo"

    def fake_enviar(tel, texto):
        return True

    monkeypatch.setattr("modo_equipo.procesar_mensaje_equipo", fake_procesar_equipo)
    monkeypatch.setattr(chat, "enviar_mensaje_whatsapp", fake_enviar)

    chat.procesar_mensaje_ia("5233123456789", "Resume este PDF")

    assert len(llamadas) == 1
    assert llamadas[0] == ("5233123456789", "Resume este PDF")


def test_preparar_contenido_equipo_salta_flujo_paciente(monkeypatch):
    monkeypatch.setenv("ENABLE_MODO_EQUIPO", "1")
    monkeypatch.setenv("WHATSAPP_ALESSANDRO", "5233123456789")

    import importlib

    import config
    import servidor

    importlib.reload(config)
    importlib.reload(servidor)

    mensaje = {
        "from": "5233123456789",
        "type": "text",
        "text": {"body": "MI CITA"},
    }
    resultado = servidor._preparar_contenido_mensaje(mensaje)
    assert resultado == "MI CITA"
