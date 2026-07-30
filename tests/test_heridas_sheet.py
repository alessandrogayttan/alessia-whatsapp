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


def test_app_config_kv(db_temp):
    storage.guardar_app_config("id_hoja_heridas", "abc123")
    assert storage.obtener_app_config("id_hoja_heridas") == "abc123"
    storage.guardar_app_config("id_hoja_heridas", "xyz")
    assert storage.obtener_app_config("id_hoja_heridas") == "xyz"
    assert storage.obtener_app_config("no_existe", "def") == "def"
