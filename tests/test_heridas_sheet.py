"""Tests hoja taller heridas."""
import storage
from heridas_sheet import _es_presencial, es_taller_heridas


def test_es_taller_heridas():
    assert es_taller_heridas("Sanando tus heridas del pasado")
    assert es_taller_heridas("taller de heridas")
    assert es_taller_heridas("Taller del niño interior")
    assert not es_taller_heridas("Alianza 360")
    assert not es_taller_heridas("Mente en Capítulos")


def test_es_presencial_cupo():
    assert _es_presencial("Presencial Zapopan")
    assert _es_presencial("Por confirmar")
    assert _es_presencial("")
    assert not _es_presencial("Online Zoom")
    assert not _es_presencial("En línea 5 semanas")


def test_headers_cupo_constantes():
    from heridas_sheet import CUPO_PRESENCIAL, HEADERS_INSCRITOS, HEADERS_INTERESADOS

    assert CUPO_PRESENCIAL == 100
    assert "WhatsApp" in HEADERS_INSCRITOS
    assert "Consulta" in HEADERS_INTERESADOS


def test_app_config_kv(db_temp):
    storage.guardar_app_config("id_hoja_heridas", "abc123")
    assert storage.obtener_app_config("id_hoja_heridas") == "abc123"
    storage.guardar_app_config("id_hoja_heridas", "xyz")
    assert storage.obtener_app_config("id_hoja_heridas") == "xyz"
    assert storage.obtener_app_config("no_existe", "def") == "def"


def test_es_pedido_sync_panel_heridas():
    from heridas_sheet import es_pedido_sync_panel_heridas

    assert es_pedido_sync_panel_heridas("sincroniza la hoja de heridas")
    assert es_pedido_sync_panel_heridas("Actualiza el panel heridas por favor")
    assert es_pedido_sync_panel_heridas("llena Heridas_Cupo")
    assert es_pedido_sync_panel_heridas("sync heridas")
    assert not es_pedido_sync_panel_heridas("info del taller de heridas")
    assert not es_pedido_sync_panel_heridas("sincroniza analytics")


def test_comando_sync_requiere_modo_pro(monkeypatch, db_temp):
    from heridas_sheet import intentar_comando_sync_heridas

    monkeypatch.setattr(
        "heridas_sheet.sincronizar_panel_heridas",
        lambda: "ÉXITO: ok",
    )
    # Sin Modo Pro: no ejecuta (aunque sea número de staff)
    assert (
        intentar_comando_sync_heridas(
            "523310265936", "sincroniza la hoja de heridas", requerir_modo_pro=True
        )
        is None
    )
    # Con sesión Modo Pro: sí
    storage.activar_sesion_equipo("523310265936", "Sara Rosales", 12)
    out = intentar_comando_sync_heridas(
        "523310265936", "sincroniza la hoja de heridas", requerir_modo_pro=True
    )
    assert out and "ÉXITO" in out and "Sara" in out


def test_pregunta_estado_sync_heridas(db_temp):
    from heridas_sheet import (
        es_pregunta_estado_sync_heridas,
        marcar_sync_heridas_pendiente,
        responder_estado_sync_heridas,
        limpiar_sync_heridas_pendiente,
    )

    assert es_pregunta_estado_sync_heridas("Ya quedó?")
    assert es_pregunta_estado_sync_heridas("ya está listo")
    assert not es_pregunta_estado_sync_heridas("quiero info del taller de heridas")

    tel = "523310265936"
    marcar_sync_heridas_pendiente(tel)
    assert "proceso" in responder_estado_sync_heridas(tel).lower()
    limpiar_sync_heridas_pendiente(tel)
    storage.guardar_app_config("heridas_sync_ok", "2026-07-30 18:00")
    storage.guardar_app_config("heridas_sync_error", "")
    assert "listo" in responder_estado_sync_heridas(tel).lower()
