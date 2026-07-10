"""Chat web — canal separado de WhatsApp."""
import json

import pytest

import storage
import web_chat


@pytest.fixture
def web_chat_habilitado(monkeypatch):
    monkeypatch.setattr("config.ENABLE_WEB_CHAT", True)
    monkeypatch.setattr("web_chat.config.ENABLE_WEB_CHAT", True)
    monkeypatch.setattr("web_chat_api.config.ENABLE_WEB_CHAT", True)


def test_sesion_web_valida_uuid():
    assert web_chat.sesion_valida("550e8400-e29b-41d4-a716-446655440000")
    assert not web_chat.sesion_valida("invalid")


def test_extraer_telefono_mexico():
    assert web_chat._extraer_telefono_de_mensaje("mi whats es 33 2445 3536") == "523324453536"
    assert web_chat._extraer_telefono_de_mensaje("hola") is None


def test_crear_sesion_storage(db_temp):
    sid = "550e8400-e29b-41d4-a716-446655440000"
    storage.crear_sesion_web(sid)
    row = storage.obtener_sesion_web(sid)
    assert row["session_id"] == sid


def test_api_desactivada_por_defecto(monkeypatch):
    monkeypatch.setattr("config.ENABLE_WEB_CHAT", False)
    monkeypatch.setattr("web_chat_api.config.ENABLE_WEB_CHAT", False)
    from servidor import app

    client = app.test_client()
    assert client.post("/api/web-chat/session").status_code == 404


def test_api_session_cuando_activo(web_chat_habilitado, db_temp, monkeypatch):
    from servidor import app

    monkeypatch.setattr("web_chat_api._origen_permitido", lambda: True)
    monkeypatch.setattr("web_chat_api._rate_limit_ok", lambda: True)

    client = app.test_client()
    r = client.post("/api/web-chat/session")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert "session_id" in data
    assert web_chat.sesion_valida(data["session_id"])


def test_api_mensaje_mock_gemini(web_chat_habilitado, db_temp, monkeypatch):
    from servidor import app

    monkeypatch.setattr("web_chat_api._origen_permitido", lambda: True)
    monkeypatch.setattr("web_chat_api._rate_limit_ok", lambda: True)
    monkeypatch.setattr(
        "web_chat_api.procesar_mensaje_web",
        lambda sid, msg, **kwargs: f"Eco web: {msg}",
    )

    sid = web_chat.nueva_sesion_web()
    client = app.test_client()
    r = client.post(
        "/api/web-chat/message",
        json={"session_id": sid, "message": "hola"},
    )
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["reply"] == "Eco web: hola"


def test_rate_limit_web(db_temp):
    ip = "test-ip-hash"
    assert storage.registrar_hit_web_chat(ip, 3) is True
    assert storage.registrar_hit_web_chat(ip, 3) is True
    assert storage.registrar_hit_web_chat(ip, 3) is True
    assert storage.registrar_hit_web_chat(ip, 3) is False


def test_widget_estatico_existe():
    from pathlib import Path

    p = Path(__file__).resolve().parent.parent / "static" / "web-chat" / "widget.js"
    assert p.is_file()
    assert "alessia-launcher" in p.read_text(encoding="utf-8")
