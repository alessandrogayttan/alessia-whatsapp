"""Tests modo equipo interno — acceso por contraseña."""
import importlib

import config
import storage


def _reload_config(monkeypatch, db_path=None, **env):
    if db_path is None:
        import config as cfg

        db_path = cfg.DATABASE_PATH
    monkeypatch.delenv("EQUIPO_CLAVE_HASH", raising=False)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    importlib.reload(config)
    monkeypatch.setattr(config, "DATABASE_PATH", db_path)
    storage.init_db()


def test_instrucciones_equipo_identidad():
    from modo_equipo import _instrucciones_equipo

    texto = _instrucciones_equipo("Alessandro")
    assert "Alessandro Gaytán" in texto
    assert "Google DeepMind" in texto
    assert "PROHIBIDO decir que eres Gemini" in texto
    assert "Tu nombre es *Alessia*" in texto


def test_preflight_entrada_frase_natural(monkeypatch, db_temp):
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="clave-test-300",
    )
    from modo_equipo import procesar_preflight_equipo

    respuesta = procesar_preflight_equipo(
        "5233123456789",
        "Quiero entrar al equipo, soy Alessandro",
    )
    assert respuesta is not None
    assert "contraseña" in respuesta.lower()


def test_clave_sin_default_inseguro(monkeypatch):
    monkeypatch.delenv("EQUIPO_CLAVE_ACCESO", raising=False)
    monkeypatch.delenv("EQUIPO_CLAVE_HASH", raising=False)
    importlib.reload(config)
    assert config.EQUIPO_CLAVE_ACCESO == ""
    assert config.secreto_modo_equipo() == ""


def test_identificar_miembro_equipo_solo_nombre(monkeypatch):
    _reload_config(monkeypatch, WHATSAPP_ALESSANDRO="5233123456789")
    assert config.identificar_miembro_equipo("5233123456789") == "Alessandro"
    assert config.identificar_miembro_equipo("5233999999999") is None


def test_preflight_pide_clave(monkeypatch, db_temp):
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="inpulso2026",
    )
    from modo_equipo import procesar_preflight_equipo

    respuesta = procesar_preflight_equipo("5233123456789", "MODO EQUIPO")
    assert respuesta is not None
    assert "contraseña" in respuesta.lower()
    assert storage.esperando_clave_equipo("5233123456789")


def test_preflight_clave_correcta_activa_sesion(monkeypatch, db_temp):
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="inpulso2026",
        WHATSAPP_ALESSANDRO="5233123456789",
        EQUIPO_SESION_HORAS="8",
    )
    from modo_equipo import MARCADOR_IA, procesar_preflight_equipo, sesion_equipo_activa

    procesar_preflight_equipo("5233123456789", "MODO EQUIPO")
    respuesta = procesar_preflight_equipo("5233123456789", "inpulso2026")
    assert respuesta is not None
    assert "activado" in respuesta.lower()
    assert sesion_equipo_activa("5233123456789")
    assert procesar_preflight_equipo("5233123456789", "Hola") == MARCADOR_IA


def test_preflight_clave_con_hash(monkeypatch, db_temp):
    from seguridad import hash_clave

    hashed = hash_clave("supersecreta")
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_HASH=hashed,
        EQUIPO_CLAVE_ACCESO="",
    )
    from modo_equipo import procesar_preflight_equipo, sesion_equipo_activa

    procesar_preflight_equipo("5233123456789", "MODO EQUIPO")
    respuesta = procesar_preflight_equipo("5233123456789", "supersecreta")
    assert respuesta is not None
    assert "activado" in respuesta.lower()
    assert sesion_equipo_activa("5233123456789")


def test_preflight_clave_incorrecta(monkeypatch, db_temp):
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="inpulso2026",
    )
    from modo_equipo import procesar_preflight_equipo, sesion_equipo_activa

    procesar_preflight_equipo("5233123456789", "MODO EQUIPO")
    respuesta = procesar_preflight_equipo("5233123456789", "mala")
    assert respuesta is not None
    assert "incorrecta" in respuesta.lower()
    assert not sesion_equipo_activa("5233123456789")


def test_salir_equipo_cierra_sesion(monkeypatch, db_temp):
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="inpulso2026",
    )
    from modo_equipo import procesar_preflight_equipo, sesion_equipo_activa

    storage.activar_sesion_equipo("5233123456789", "Equipo", 12)
    assert sesion_equipo_activa("5233123456789")
    respuesta = procesar_preflight_equipo("5233123456789", "SALIR EQUIPO")
    assert respuesta is not None
    assert "salí" in respuesta.lower()
    assert not sesion_equipo_activa("5233123456789")


def test_procesar_mensaje_ia_rutea_equipo_con_sesion(monkeypatch, db_temp):
    _reload_config(
        monkeypatch, db_temp, ENABLE_MODO_EQUIPO="1", EQUIPO_CLAVE_ACCESO="inpulso2026"
    )
    import chat

    importlib.reload(chat)
    storage.activar_sesion_equipo("5233123456789", "Alessandro", 12)

    llamadas: list[tuple] = []

    def fake_procesar_equipo(tel, contenido):
        llamadas.append((tel, contenido))
        return "Respuesta equipo"

    def fake_enviar(tel, texto):
        return True

    monkeypatch.setattr("modo_equipo.procesar_mensaje_equipo", fake_procesar_equipo)
    monkeypatch.setattr(chat, "enviar_mensaje_whatsapp", fake_enviar)

    chat.procesar_mensaje_ia("5233123456789", "Resume este PDF")
    assert llamadas == [("5233123456789", "Resume este PDF")]


def test_preparar_contenido_sin_sesion_usa_flujo_paciente(monkeypatch, db_temp):
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="inpulso2026",
        WHATSAPP_ALESSANDRO="5233123456789",
    )
    import servidor

    importlib.reload(servidor)
    monkeypatch.setattr(config, "DATABASE_PATH", db_temp)

    mensaje = {
        "from": "5233123456789",
        "type": "text",
        "text": {"body": "MODO EQUIPO"},
    }
    resultado = servidor._preparar_contenido_mensaje(mensaje)
    assert resultado is None
