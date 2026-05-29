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
