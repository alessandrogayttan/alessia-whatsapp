"""Botones Quick Reply de plantillas de recordatorio."""
import storage
from experiencia import procesar_boton_recordatorio, respuesta_confirmar_asistencia


def test_confirmar_asistencia_registra_y_responde(monkeypatch):
    cita = {
        "event_id": "evt-123",
        "fecha": "2026-07-10",
        "hora": "10:00",
        "especialista": "Sara Rosales",
    }
    monkeypatch.setattr(
        "experiencia.listar_citas_futuras_por_telefono",
        lambda tel: [cita],
    )
    monkeypatch.setattr(storage, "primer_nombre", lambda tel: "María")
    monkeypatch.setattr(storage, "obtener_nombre_paciente", lambda tel: None)
    monkeypatch.setattr(storage, "asistencia_ya_confirmada", lambda e, t: False)

    marcado = []

    def _marcar(telefono, event_id, fecha, hora, esp):
        marcado.append((telefono, event_id))

    monkeypatch.setattr(storage, "marcar_asistencia_confirmada", _marcar)

    msg = respuesta_confirmar_asistencia("523300000001")
    assert "Asistencia confirmada" in msg
    assert "María" in msg
    assert marcado == [("523300000001", "evt-123")]


def test_procesar_boton_reagendar_ofrece_opciones(monkeypatch):
    cita = {
        "event_id": "evt-456",
        "fecha": "2026-07-10",
        "hora": "10:00",
        "especialista": "Sara Rosales",
    }
    monkeypatch.setattr(
        "experiencia.listar_citas_futuras_por_telefono",
        lambda tel: [cita],
    )
    monkeypatch.setattr(
        "experiencia._opciones_horarios_alternativos",
        lambda esp, max_opciones=3: ["2026-07-11 a las 11:00", "2026-07-12 a las 09:00"],
    )
    monkeypatch.setattr(storage, "marcar_reagendar_pendiente", lambda t, e: None)

    msg = procesar_boton_recordatorio("523300000001", "Necesito reagendar")
    assert msg is not None
    assert "1." in msg
    assert "2." in msg


def test_procesar_boton_desconocido_devuelve_none():
    assert procesar_boton_recordatorio("523300000001", "hola") is None
