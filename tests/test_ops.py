"""Tests de confiabilidad / ops: cola, health, backup, WhatsApp retries."""
from __future__ import annotations

from datetime import timedelta

import config
import storage


def test_reencolar_procesando_atascados(db_temp):
    msg_id = storage.encolar_mensaje_ia("523311111111", "hola")
    assert storage.marcar_mensaje_procesando(msg_id)
    # Simular atasco antiguo
    viejo = (storage._utcnow() - timedelta(minutes=30)).isoformat()
    with storage._transaction() as conn:
        conn.execute(
            "UPDATE cola_mensajes SET actualizado_at = ? WHERE id = ?",
            (viejo, msg_id),
        )
    n = storage.reencolar_mensajes_procesando_atascados(minutos=10)
    assert n == 1
    with storage._transaction() as conn:
        row = conn.execute(
            "SELECT estado FROM cola_mensajes WHERE id = ?", (msg_id,)
        ).fetchone()
    assert row["estado"] == "pendiente"


def test_reclamar_recordatorio_atomico(db_temp):
    assert storage.reclamar_recordatorio("evt-1", "24h") is True
    assert storage.reclamar_recordatorio("evt-1", "24h") is False
    storage.liberar_recordatorio("evt-1", "24h")
    assert storage.reclamar_recordatorio("evt-1", "24h") is True


def test_backup_sqlite_online(tmp_path, db_temp):
    from db_backup import backup_sqlite

    dest = tmp_path / "alessia_20260101.db"
    backup_sqlite(config.DATABASE_PATH, dest)
    assert dest.is_file()
    assert dest.stat().st_size > 0
    # Verificar que el backup es SQLite legible
    import sqlite3

    with sqlite3.connect(dest) as conn:
        row = conn.execute("SELECT 1").fetchone()
    assert row[0] == 1


def test_prune_backups(tmp_path):
    from db_backup import prune_backups

    for i in range(3):
        p = tmp_path / f"alessia_2026010{i}.db"
        p.write_bytes(b"sqlite-fake")
    assert prune_backups(tmp_path, keep=1) == 2
    assert len(list(tmp_path.glob("alessia_*.db"))) == 1


def test_health_ready_ok(monkeypatch):
    import servidor

    monkeypatch.setattr(servidor.config, "TOKEN_WHATSAPP", "t")
    monkeypatch.setattr(servidor.config, "GEMINI_API_KEY", "g")
    monkeypatch.setattr(servidor.config, "ID_TELEFONO", "1")
    monkeypatch.setattr(servidor.config, "GOOGLE_SERVICE_ACCOUNT_JSON", '{"type":"x"}')
    monkeypatch.setattr(servidor.storage, "ping_db", lambda: True)
    monkeypatch.setattr(servidor.storage, "init_db", lambda: None)
    resp = servidor.app.test_client().get("/health/ready")
    assert resp.status_code == 200
    assert resp.get_json()["ready"] is True


def test_health_ready_falta_token(monkeypatch):
    import servidor

    monkeypatch.setattr(servidor.config, "TOKEN_WHATSAPP", "")
    monkeypatch.setattr(servidor.config, "GEMINI_API_KEY", "g")
    monkeypatch.setattr(servidor.config, "ID_TELEFONO", "1")
    monkeypatch.setattr(servidor.config, "GOOGLE_SERVICE_ACCOUNT_JSON", '{"type":"x"}')
    monkeypatch.setattr(servidor.storage, "ping_db", lambda: True)
    monkeypatch.setattr(servidor.storage, "init_db", lambda: None)
    resp = servidor.app.test_client().get("/health/ready")
    assert resp.status_code == 503
    assert "TOKEN_WHATSAPP" in resp.get_json()["bloqueantes"]


def test_whatsapp_retry_429_then_ok(monkeypatch):
    import whatsapp

    monkeypatch.setattr(whatsapp.config, "TOKEN_WHATSAPP", "tok")
    monkeypatch.setattr(whatsapp.config, "ID_TELEFONO", "123")
    monkeypatch.setattr(whatsapp.config, "WHATSAPP_SEND_RETRIES", 3)
    monkeypatch.setattr(whatsapp.time, "sleep", lambda *_: None)

    calls = {"n": 0}

    class FakeResp:
        def __init__(self, code):
            self.status_code = code
            self.text = "rate"
            self.headers = {"Retry-After": "1"}

    def fake_post(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp(429)
        return FakeResp(200)

    monkeypatch.setattr(whatsapp.requests, "post", fake_post)
    ok = whatsapp._enviar_payload("523311111111", {"type": "text", "text": {"body": "hi"}})
    assert ok is True
    assert calls["n"] == 2


def test_whatsapp_registra_fallo_final(monkeypatch):
    import whatsapp
    from observability import metricas_fallos

    before = metricas_fallos()["fallos_whatsapp_1h"]
    monkeypatch.setattr(whatsapp.config, "TOKEN_WHATSAPP", "tok")
    monkeypatch.setattr(whatsapp.config, "ID_TELEFONO", "123")
    monkeypatch.setattr(whatsapp.config, "WHATSAPP_SEND_RETRIES", 2)
    monkeypatch.setattr(whatsapp.time, "sleep", lambda *_: None)

    class FakeResp:
        status_code = 500
        text = "err"
        headers = {}

    monkeypatch.setattr(whatsapp.requests, "post", lambda *_a, **_k: FakeResp())
    ok = whatsapp._enviar_payload("523399999999", {"type": "text", "text": {"body": "x"}})
    assert ok is False
    after = metricas_fallos()["fallos_whatsapp_1h"]
    assert after >= before + 1


def test_recuperar_atascados_message_queue(db_temp, monkeypatch):
    import message_queue

    msg_id = storage.encolar_mensaje_ia("523322222222", "cola")
    storage.marcar_mensaje_procesando(msg_id)
    viejo = (storage._utcnow() - timedelta(minutes=20)).isoformat()
    with storage._transaction() as conn:
        conn.execute(
            "UPDATE cola_mensajes SET actualizado_at = ? WHERE id = ?",
            (viejo, msg_id),
        )
    assert message_queue.recuperar_atascados(minutos=5) == 1
