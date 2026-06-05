from tools import (
    _extraer_montos_de_texto,
    _normalizar_telefono_digitos,
    validar_monto_pago,
)
from whatsapp import _partir_mensaje, normalizar_telefono

import pytest


def test_normalizar_telefono_whatsapp():
    assert normalizar_telefono("5213326505999") == "523326505999"


def test_normalizar_telefono_digitos():
    assert _normalizar_telefono_digitos("5213326505999") == "3326505999"
    assert _normalizar_telefono_digitos("+52 33 2650 5999") == "3326505999"


def test_extraer_montos_de_texto():
    assert 500.0 in _extraer_montos_de_texto("Online $400 MXN / Presencial $500 MXN")
    assert _extraer_montos_de_texto("$800") == [800.0]


def test_partir_mensaje_largo():
    texto = "a" * 5000
    partes = _partir_mensaje(texto, max_len=4000)
    assert len(partes) == 2
    assert all(len(p) <= 4000 for p in partes)
    assert "".join(partes) == texto


def test_validar_monto_rechaza_sin_inscripcion(monkeypatch):
    import tools

    monkeypatch.setattr(tools, "_obtener_inscripcion_pendiente", lambda t: None)
    ok, msg = validar_monto_pago("523326505999", 500.0)
    assert ok is False
    assert "PENDIENTE" in msg


def test_validar_monto_acepta_coincidencia(monkeypatch):
    import tools

    monkeypatch.setattr(
        tools,
        "_obtener_inscripcion_pendiente",
        lambda t: {"taller": "Taller X", "montos_esperados": [500.0]},
    )
    ok, msg = validar_monto_pago("523326505999", 500.0)
    assert ok is True


def test_validar_monto_rechaza_diferencia(monkeypatch):
    import tools

    monkeypatch.setattr(
        tools,
        "_obtener_inscripcion_pendiente",
        lambda t: {"taller": "Taller X", "montos_esperados": [500.0]},
    )
    ok, msg = validar_monto_pago("523326505999", 100.0)
    assert ok is False


def test_validar_fecha_cita_martes():
    from tools import validar_fecha_cita

    result = validar_fecha_cita("2026-06-02")
    assert "martes" in result
    assert "2026-06-02" in result


def test_identificar_terapeuta_sara():
    from config import identificar_terapeuta

    assert identificar_terapeuta("523310265936") == "Sara Rosales"
    assert identificar_terapeuta("5213310265936") == "Sara Rosales"


def test_es_evento_bloqueo():
    from tools import _es_evento_bloqueo

    assert _es_evento_bloqueo({"summary": "BLOQUEADO — Vacaciones", "start": {"dateTime": "x"}})
    assert _es_evento_bloqueo({"summary": "Paciente", "start": {"date": "2026-06-01"}})
    assert not _es_evento_bloqueo(
        {
            "summary": "DIEGO",
            "description": "Cita de Consulta. Teléfono: 523326505999",
            "start": {"dateTime": "2026-06-01T09:00:00-06:00"},
        }
    )


def _fijar_fecha_catalogo(monkeypatch, anio: int, mes: int, dia: int):
    import datetime

    import catalogo
    import pytz

    fijo = datetime.datetime(anio, mes, dia, 12, 0, tzinfo=pytz.timezone("America/Mexico_City"))

    class FakeDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return fijo

    monkeypatch.setattr(catalogo.datetime, "datetime", FakeDatetime)


def test_estado_taller_en_curso(monkeypatch):
    import catalogo

    _fijar_fecha_catalogo(monkeypatch, 2026, 6, 4)
    estado = catalogo.estado_taller("Lunes 1 y 8 de junio")
    assert estado["estado_taller"] == "en_curso"
    assert "YA ESTÁ EN CURSO" in estado["aviso_estado"]
    assert "08/06/2026" in estado["aviso_estado"]


def test_estado_taller_por_iniciar(monkeypatch):
    import catalogo

    _fijar_fecha_catalogo(monkeypatch, 2026, 5, 20)
    estado = catalogo.estado_taller("Lunes 1 y 8 de junio")
    assert estado["estado_taller"] == "por_iniciar"


def test_es_servicio_online():
    from tools import _es_servicio_online

    assert _es_servicio_online("Consulta online")
    assert _es_servicio_online("Terapia en línea")
    assert not _es_servicio_online("Consulta presencial")


def test_formatear_confirmacion_cita_online_incluye_pago():
    import datetime

    from tools import _formatear_confirmacion_cita

    fecha = datetime.datetime(2026, 6, 10, 10, 0)
    bloque = _formatear_confirmacion_cita(
        fecha, "Sara Rosales", "Consulta online", es_online=True
    )
    assert "en línea" in bloque.lower() or "en línea" in bloque
    assert "totalidad" in bloque.lower()
    assert "tarjeta" in bloque.lower()
    assert "botón" in bloque.lower()
    assert "zoom" in bloque.lower()
    assert "día de tu cita" in bloque.lower()
    assert "audífonos" in bloque.lower()


def test_formatear_evento_cita():
    from tools import _formatear_evento_cita

    evento = {
        "summary": "MARÍA LÓPEZ",
        "description": "Cita de Terapia con Sara Rosales. Teléfono: 523311122233",
        "start": {"dateTime": "2026-06-01T10:00:00-06:00"},
    }
    texto = _formatear_evento_cita(evento)
    assert "10:00" in texto
    assert "MARÍA LÓPEZ" in texto
    assert "523311122233" in texto
