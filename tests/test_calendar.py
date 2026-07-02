import pytest

import tools
from google_client import GoogleCalendarError


def test_fallo_calendario_no_escala_recepcion(monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        tools,
        "registrar_escalacion_humana",
        lambda tel, motivo: llamadas.append((tel, motivo)) or True,
    )

    msg = tools._respuesta_fallo_calendario(
        "Sara Rosales",
        "2026-07-02",
        GoogleCalendarError("503", http_status=503),
    )

    assert not llamadas
    assert "ERROR_CALENDARIO_TEMPORAL" in msg
    assert "consultar_agenda" in msg
    assert "recepción" not in msg.lower()


def test_obtener_eventos_dia_reintenta_y_recupera(monkeypatch):
    tools._agenda_cache.clear()
    intentos = {"n": 0}

    def fake_reintento(op, desc, deadline=None):
        intentos["n"] += 1
        if intentos["n"] < 2:
            raise GoogleCalendarError("temporal", http_status=503)
        return op()

    class FakeService:
        def events(self):
            return self

        def list(self, **kwargs):
            return self

        def execute(self):
            return {"items": [{"id": "evt1"}]}

    monkeypatch.setattr(tools.config, "CALENDAR_CONSULTA_REINTENTOS", 3)
    monkeypatch.setattr(tools.config, "CALENDAR_RETRY_PAUSE_SECONDS", 0)
    monkeypatch.setattr(tools, "ejecutar_con_reintento", fake_reintento)
    monkeypatch.setattr(tools, "get_calendar_service", lambda: FakeService())
    monkeypatch.setattr(tools, "reset_google_clients", lambda: None)
    monkeypatch.setattr(tools.time, "sleep", lambda _: None)

    items = tools._obtener_eventos_dia("cal@test", "2026-07-02", usar_cache=False)
    assert items == [{"id": "evt1"}]
    assert intentos["n"] >= 2


def test_obtener_eventos_dia_usa_cache(monkeypatch):
    tools._agenda_cache.clear()
    llamadas = {"n": 0}

    def fake_listar():
        llamadas["n"] += 1
        return {"items": [{"id": "evt1"}]}

    monkeypatch.setattr(
        tools, "ejecutar_con_reintento", lambda op, desc, deadline=None: op()
    )

    class FakeService:
        def events(self):
            return self

        def list(self, **kwargs):
            return self

        def execute(self):
            return fake_listar()

    monkeypatch.setattr(tools, "get_calendar_service", lambda: FakeService())

    cal_id = "test@group.calendar.google.com"
    fecha = "2026-07-02"
    r1 = tools._obtener_eventos_dia(cal_id, fecha)
    r2 = tools._obtener_eventos_dia(cal_id, fecha)
    assert r1 == r2 == [{"id": "evt1"}]
    assert llamadas["n"] == 1

    tools._invalidar_cache_agenda(cal_id, fecha)
    tools._obtener_eventos_dia(cal_id, fecha)
    assert llamadas["n"] == 2
