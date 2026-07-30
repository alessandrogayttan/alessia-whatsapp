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


def test_comando_sync_solo_personal(monkeypatch):
    from heridas_sheet import intentar_comando_sync_heridas

    monkeypatch.setattr(
        "heridas_sheet.sincronizar_panel_heridas",
        lambda: "ÉXITO: ok",
    )
    # Paciente: no ejecuta
    assert (
        intentar_comando_sync_heridas("5219999999999", "sincroniza la hoja de heridas")
        is None
    )
    # Staff (Sara): sí
    out = intentar_comando_sync_heridas(
        "523310265936", "sincroniza la hoja de heridas"
    )
    assert out and "Sara" in out and "ÉXITO" in out
