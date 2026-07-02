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


def test_interes_talleres_y_notificacion(db_temp):
    storage.registrar_interes_taller(
        "523326505999", "Sara Rosales", "Taller ansiedad", "María"
    )
    lista = storage.listar_interes_talleres("Sara")
    assert len(lista) == 1
    assert lista[0]["telefono"] == "523326505999"

    clave = "sara rosales|nuevo taller|junio"
    assert not storage.notificacion_nuevo_taller_enviada("523326505999", clave)
    storage.marcar_notificacion_nuevo_taller("523326505999", clave)
    assert storage.notificacion_nuevo_taller_enviada("523326505999", clave)

    storage.marcar_taller_catalogo_visto(clave)
    assert storage.taller_catalogo_ya_visto(clave)


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


def test_eliminar_datos_paciente_limpia_tablas_locales(db_temp):
    telefono = "523326505999"
    storage.guardar_nombre_paciente(telefono, "María López")
    storage.guardar_ubicacion(telefono, 20.1, -103.1)
    storage.guardar_checkin_emocional(telefono, 8)
    storage.marcar_prep_pendiente(telefono, "evt-1")
    storage.guardar_prep_sesion(telefono, "evt-1", "Ansiedad", "no", 8)
    storage.marcar_ritual_pendiente(telefono, "evt-2")
    storage.guardar_nota_ritual(telefono, "evt-2", "Me llevo calma")
    storage.registrar_primera_cita_si_nueva(telefono, "2025-05-28")
    storage.marcar_aniversario_enviado(telefono, 1)
    storage.crear_tarea_terapeutica(telefono, "523322222222", "Respirar", "lunes")
    storage.registrar_interes_taller(telefono, "Sara Rosales", "Taller ansiedad", "María")
    storage.marcar_notificacion_nuevo_taller(telefono, "sara|taller")

    storage.eliminar_datos_paciente(telefono)

    with storage._transaction() as conn:
        tablas = {
            "pacientes": "telefono",
            "ubicaciones_pacientes": "telefono",
            "paciente_extra": "telefono",
            "checkins_emocionales": "telefono",
            "prep_sesion": "telefono",
            "prep_pendiente": "telefono",
            "ritual_pendiente": "telefono",
            "notas_ritual": "telefono",
            "primera_cita": "telefono",
            "aniversarios_enviados": "telefono",
            "tareas_terapeuticas": "telefono_paciente",
            "interes_talleres": "telefono",
            "notificaciones_nuevo_taller": "telefono",
        }
        for tabla, columna in tablas.items():
            row = conn.execute(
                f"SELECT COUNT(*) AS total FROM {tabla} WHERE {columna} = ?",
                (telefono,),
            ).fetchone()
            assert row["total"] == 0, tabla
