import os
import tempfile

import pytest

import config
import storage


@pytest.fixture
def db_temp(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    storage.init_db()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


def test_reservar_mensaje_deduplica(db_temp):
    assert storage.reservar_mensaje_para_procesar("msg-001") is True
    assert storage.reservar_mensaje_para_procesar("msg-001") is False


def test_resetear_menciones_proactivas(db_temp):
    storage.marcar_cita_proactiva_mencionada("523326505999", "2026-06-01_10:00_Sara")
    assert storage.ya_menciono_cita_proactiva("523326505999", "2026-06-01_10:00_Sara")
    storage.resetear_menciones_proactivas("523326505999")
    assert not storage.ya_menciono_cita_proactiva("523326505999", "2026-06-01_10:00_Sara")


def test_obtener_nombre_paciente(db_temp):
    storage.guardar_nombre_paciente("523326505999", "María")
    assert storage.obtener_nombre_paciente("523326505999") == "María"
