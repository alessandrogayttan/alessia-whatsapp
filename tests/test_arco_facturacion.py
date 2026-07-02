import storage
from tools import validar_cuenta_destino


def test_validar_cuenta_destino_banorte():
    assert validar_cuenta_destino("072320003548248000") is True


def test_validar_cuenta_destino_banamex():
    assert validar_cuenta_destino("002320700928855166") is True


def test_validar_cuenta_destino_invalida():
    assert validar_cuenta_destino("123456789012345678") is False


def test_registrar_consentimiento(db_temp):
    assert storage.necesita_consentimiento("523326505999") is True
    storage.registrar_consentimiento("523326505999")
    assert storage.necesita_consentimiento("523326505999") is False


def test_registrar_solicitud_facturacion_sin_hoja(monkeypatch):
    import config
    import tools

    monkeypatch.setattr(config, "ID_HOJA_CALCULO", "")
    resultado = tools.registrar_solicitud_facturacion(
        "523326505999",
        "Empresa SA",
        "ABC123456ABC",
        "Calle 1, Col, CP 45100",
        "2026-06-10",
        "10:00",
        "Transferencia",
        "Gastos en general",
    )
    assert "fallo técnico" in resultado.lower() or "no pude" in resultado.lower()
