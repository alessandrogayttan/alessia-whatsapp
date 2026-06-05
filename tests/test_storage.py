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


def test_ping_db(db_temp):
    assert storage.ping_db() is True


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


def test_memoria_nombre_por_telefono(db_temp):
    storage.guardar_nombre_casual("523326505999", "Alessandro")
    assert storage.primer_nombre("523326505999") == "Alessandro"
    assert not storage.tiene_nombre_completo("523326505999")
    storage.guardar_nombre_paciente("523326505999", "Alessandro Gaytán")
    assert storage.tiene_nombre_completo("523326505999")
    storage.guardar_nombre_casual("523326505999", "Alex")
    assert storage.obtener_nombre_paciente("523326505999") == "Alessandro Gaytán"


def test_prep_sesion_y_pendiente(db_temp):
    storage.marcar_prep_pendiente("523326505999", "evt-1")
    assert storage.obtener_prep_pendiente("523326505999") == "evt-1"
    storage.guardar_prep_sesion("523326505999", "evt-1", "Ansiedad laboral", "no", 7)
    assert storage.obtener_prep_pendiente("523326505999") is None
    prep = storage.obtener_prep_sesion_reciente("523326505999")
    assert prep["tema"] == "Ansiedad laboral"
    assert prep["animo"] == 7


def test_ritual_cierre(db_temp):
    storage.marcar_ritual_pendiente("523326505999", "evt-2")
    storage.guardar_nota_ritual("523326505999", "evt-2", "Me llevo más calma")
    assert storage.obtener_ritual_pendiente("523326505999") is None


def test_tareas_terapeuticas(db_temp):
    from datetime import datetime

    hoy = datetime.utcnow().strftime("%Y-%m-%d")
    tid = storage.crear_tarea_terapeutica(
        "523311111111", "523322222222", "Respirar 5 min", "lunes,miercoles"
    )
    assert tid > 0
    tareas = storage.tareas_pendientes_hoy("lunes")
    assert any(t["id"] == tid for t in tareas)
    storage.marcar_tarea_enviada_hoy(tid, hoy)
    tareas_despues = storage.tareas_pendientes_hoy("lunes")
    assert not any(t["id"] == tid for t in tareas_despues)


def test_primera_cita_y_aniversario(db_temp):
    storage.registrar_primera_cita_si_nueva("523326505999", "2025-05-28")
    storage.registrar_primera_cita_si_nueva("523326505999", "2025-06-01")
    fechas = dict(storage.listar_primeras_citas())
    assert fechas["523326505999"] == "2025-05-28"
    assert not storage.aniversario_ya_enviado("523326505999", 1)
    storage.marcar_aniversario_enviado("523326505999", 1)
    assert storage.aniversario_ya_enviado("523326505999", 1)
