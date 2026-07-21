import config
import storage
from tools import validar_cuenta_destino


def test_validar_cuenta_destino_banorte():
    clabe = config.CUENTAS_OFICIALES["BANORTE"]["clabe"]
    assert clabe
    assert validar_cuenta_destino(clabe) is True


def test_validar_cuenta_destino_banamex():
    clabe = config.CUENTAS_OFICIALES["BANAMEX"]["clabe"]
    assert clabe
    assert validar_cuenta_destino(clabe) is True


def test_validar_cuenta_destino_invalida():
    assert validar_cuenta_destino("123456789012345678") is False


def test_registrar_consentimiento(db_temp):
    assert storage.necesita_consentimiento("523326505999") is True
    storage.registrar_consentimiento("523326505999")
    assert storage.necesita_consentimiento("523326505999") is False


def test_registrar_solicitud_facturacion_sin_hoja(monkeypatch):
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
