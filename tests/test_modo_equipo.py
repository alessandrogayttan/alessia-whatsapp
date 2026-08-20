"""Tests Modo Pro (antes modo equipo) — acceso por contraseña."""
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
    assert "Modo Pro" in texto
    assert "PDF" in texto
    assert "guardar_conocimiento_pacientes" in texto
    assert "BANORTE" in texto or "formas de *pago*" in texto
    assert "PROHIBIDO decir que no las tienes" in texto


def test_modo_pro_responde_pagos_sin_pedirlos(db_temp, monkeypatch):
    from modo_equipo import activar_sesion_equipo, procesar_mensaje_equipo

    tel = "523399988877"
    activar_sesion_equipo(tel, "Recepción")
    out = procesar_mensaje_equipo(tel, "dame las formas de pago de Inpulso para citas online")
    assert out
    assert "BANORTE" in out and "CLABE" in out
    assert "proporcion" not in out.lower()


def test_modo_pro_recuerda_info_pero_deja_agregar(db_temp):
    from modo_equipo import (
        _es_pedido_ensenar_o_agregar,
        _respuesta_rapida_equipo,
        activar_sesion_equipo,
        procesar_mensaje_equipo,
    )

    assert _es_pedido_ensenar_o_agregar("guarda que el taller cuesta 3000")
    assert not _es_pedido_ensenar_o_agregar("¿cuánto cuesta con Sara?")
    # Recuerdo: respuesta rápida
    assert _respuesta_rapida_equipo("¿formas de pago?")
    # Enseñar: no interceptar (Gemini + tool)
    assert _respuesta_rapida_equipo("agrega: el club de lectura ahora es jueves") is None

    tel = "523399988866"
    activar_sesion_equipo(tel, "Recepción")
    out = procesar_mensaje_equipo(tel, "¿dónde está Inpulso?")
    assert out and ("Hidalgo" in out or "Zapopan" in out or "ubicación" in out.lower() or "dirección" in out.lower() or "Av." in out)


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
        "Quiero modo pro, soy Alessandro",
    )
    assert respuesta is not None
    assert "contraseña" in respuesta.lower()
    assert "modo pro" in respuesta.lower()


def test_preflight_no_reabre_por_mencion_modo_pro(monkeypatch, db_temp):
    """Mencionar Modo Pro en una frase larga no debe pedir contraseña otra vez."""
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="clave-test-300",
    )
    from modo_equipo import procesar_preflight_equipo

    respuesta = procesar_preflight_equipo(
        "5233123456789",
        "Estábamos en el modo pro sincronizando la hoja de heridas",
    )
    assert respuesta is None


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

    respuesta = procesar_preflight_equipo("5233123456789", "MODO PRO")
    assert respuesta is not None
    assert "contraseña" in respuesta.lower()
    assert "modo pro" in respuesta.lower()
    assert storage.esperando_clave_equipo("5233123456789")


def test_preflight_alias_legacy_modo_equipo(monkeypatch, db_temp):
    """«MODO EQUIPO» sigue funcionando como alias."""
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


def test_preflight_clave_correcta_activa_sesion(monkeypatch, db_temp):
    """Número externo (no staff): sigue el flujo contraseña → sesión."""
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="inpulso2026",
        WHATSAPP_ALESSANDRO="",
        EQUIPO_SESION_HORAS="8",
    )
    from modo_equipo import MARCADOR_IA, procesar_preflight_equipo, sesion_equipo_activa

    tel = "529998887766"
    procesar_preflight_equipo(tel, "MODO PRO")
    respuesta = procesar_preflight_equipo(tel, "inpulso2026")
    assert respuesta is not None
    assert "listo" in respuesta.lower() or "activado" in respuesta.lower()
    assert "modo pro" in respuesta.lower()
    assert sesion_equipo_activa(tel)
    assert procesar_preflight_equipo(tel, "Hola") == MARCADOR_IA


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

    procesar_preflight_equipo("5233123456789", "MODO PRO")
    respuesta = procesar_preflight_equipo("5233123456789", "supersecreta")
    assert respuesta is not None
    assert "listo" in respuesta.lower() or "activado" in respuesta.lower()
    assert sesion_equipo_activa("5233123456789")


def test_preflight_clave_incorrecta(monkeypatch, db_temp):
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="inpulso2026",
    )
    from modo_equipo import procesar_preflight_equipo, sesion_equipo_activa

    procesar_preflight_equipo("5233123456789", "MODO PRO")
    respuesta = procesar_preflight_equipo("5233123456789", "mala")
    assert respuesta is not None
    assert "incorrecta" in respuesta.lower()
    assert not sesion_equipo_activa("5233123456789")


def test_salir_pro_cierra_sesion(monkeypatch, db_temp):
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="inpulso2026",
    )
    from modo_equipo import procesar_preflight_equipo, sesion_equipo_activa

    storage.activar_sesion_equipo("5233123456789", "Equipo", 12)
    assert sesion_equipo_activa("5233123456789")
    respuesta = procesar_preflight_equipo("5233123456789", "SALIR PRO")
    assert respuesta is not None
    assert "salí" in respuesta.lower()
    assert "modo pro" in respuesta.lower()
    assert not sesion_equipo_activa("5233123456789")


def test_salir_pro_sin_sesion_responde_claro(monkeypatch, db_temp):
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="inpulso2026",
    )
    from modo_equipo import procesar_preflight_equipo

    respuesta = procesar_preflight_equipo("5233123456789", "SALIR PRO")
    assert respuesta is not None
    assert "modo pro" in respuesta.lower()
    assert "no había" in respuesta.lower() or "no habia" in respuesta.lower()


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


def test_sara_auto_modo_pro_sin_contraseña(monkeypatch, db_temp):
    """Sara (terapeuta) entra a Modo Pro sin pedir clave."""
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="clave-test-300",
        WHATSAPP_SARA="523310265936",
    )
    from modo_equipo import (
        MARCADOR_IA,
        _nombre_miembro,
        asegurar_privilegios_staff,
        procesar_preflight_equipo,
        sesion_equipo_activa,
    )

    tel = "523310265936"
    assert asegurar_privilegios_staff(tel) is True
    assert sesion_equipo_activa(tel)
    assert _nombre_miembro(tel) == "Sara Rosales"
    assert procesar_preflight_equipo(tel, "¿tengo citas el lunes?") == MARCADOR_IA
    assert procesar_preflight_equipo(tel, "sincroniza la hoja de heridas") == MARCADOR_IA


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
        "text": {"body": "MODO PRO"},
    }
    resultado = servidor._preparar_contenido_mensaje(mensaje)
    assert resultado is None


def test_sync_heridas_modo_pro_confirma_sin_revalidar_sesion(monkeypatch, db_temp):
    """Modo Pro encola sync durable (no hilo daemon)."""
    _reload_config(
        monkeypatch,
        db_temp,
        ENABLE_MODO_EQUIPO="1",
        EQUIPO_CLAVE_ACCESO="inpulso2026",
        WHATSAPP_ALESSANDRO="5233123456789",
    )
    import whatsapp_inbound as wi

    tel = "5233123456789"
    storage.activar_sesion_equipo(tel, "Alessandro", 12)
    enviados = []
    monkeypatch.setattr(
        wi, "enviar_mensaje_whatsapp", lambda t, m: enviados.append((t, m))
    )

    mensaje = {
        "from": tel,
        "type": "text",
        "text": {"body": "sincroniza la hoja de heridas"},
    }
    assert wi.preparar_contenido_mensaje(mensaje) is None
    textos = " ".join(m for _, m in enviados)
    assert "Encolé" in textos or "encolé" in textos.lower()
    job = storage.ultimo_trabajo_telefono(tel, "sync_heridas")
    assert job and job["estado"] == "pendiente"
