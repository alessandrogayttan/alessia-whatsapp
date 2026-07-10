"""Escalación a recepción / HABLAR CON PERSONA."""
from escalacion import es_solicitud_humano, mensaje_confirmacion_escalacion


def test_detecta_hablar_con_persona():
    assert es_solicitud_humano("HABLAR CON PERSONA")
    assert es_solicitud_humano("Quiero hablar con alguien")
    assert es_solicitud_humano("necesito hablar con recepción")
    assert es_solicitud_humano("pásame con una persona por favor")
    assert not es_solicitud_humano("Hola, quiero info de precios")
    assert not es_solicitud_humano("¿Quién es Sara Rosales?")


def test_mensaje_confirmacion_segun_estado():
    ok = mensaje_confirmacion_escalacion(True, True)
    assert "avisé" in ok.lower() or "avise" in ok.lower()
    sin_cfg = mensaje_confirmacion_escalacion(False, False)
    assert "33 1469" in sin_cfg or "1469" in sin_cfg


def test_recepcion_se_normaliza(monkeypatch):
    monkeypatch.setenv("RECEPCION_WHATSAPP", "+52 33 1234 5678")
    import importlib

    import config

    importlib.reload(config)
    assert config.RECEPCION_WHATSAPP == "523312345678"


def test_escalar_avisa_aunque_falle_sheets(monkeypatch, db_temp):
    import tools

    monkeypatch.setattr(tools.config, "RECEPCION_WHATSAPP", "523399988877")
    monkeypatch.setattr(tools.config, "ID_HOJA_CALCULO", "fake")
    monkeypatch.setattr(tools.config, "WHATSAPP_TEMPLATE_ESCALACION", "")

    def boom(*a, **k):
        raise RuntimeError("sheets down")

    monkeypatch.setattr(tools, "get_sheets_service", boom)

    enviados = []

    def fake_recordatorio(tel, texto, plantilla="", params=None):
        enviados.append((tel, texto))
        return True

    monkeypatch.setattr("whatsapp.enviar_recordatorio", fake_recordatorio)

    msg = tools.registrar_escalacion_humana("523311122233", "Prueba")
    assert enviados
    assert enviados[0][0] == "523399988877"
    assert "notificada" in msg.lower() or "avisada" in msg.lower()


def test_normalizar_telefono_limpia_simbolos():
    from whatsapp import normalizar_telefono

    assert normalizar_telefono("+52 33 2650 5999") == "523326505999"
    assert normalizar_telefono("5213326505999") == "523326505999"
