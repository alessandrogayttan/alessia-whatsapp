"""MI CITA, NPS post-cita y marca."""
import storage
from experiencia import mensaje_mi_cita, respuesta_seguimiento_nps
from marca import contexto_blog_si_aplica, mensaje_codigo_referido


def test_mi_cita_sin_citas(monkeypatch):
    monkeypatch.setattr(
        "experiencia.listar_citas_futuras_por_telefono",
        lambda tel: [],
    )
    msg = mensaje_mi_cita("523300000001")
    assert "No encontré" in msg


def test_mi_cita_con_datos(monkeypatch):
    cita = {
        "fecha": "2026-07-10",
        "hora": "10:00",
        "especialista": "Sara Rosales",
        "servicio": "Consulta individual",
        "resumen": "Cita",
    }
    monkeypatch.setattr(
        "experiencia.listar_citas_futuras_por_telefono",
        lambda tel: [cita],
    )
    monkeypatch.setattr(storage, "primer_nombre", lambda tel: "María")
    msg = mensaje_mi_cita("523300000001")
    assert "Tu próxima cita" in msg
    assert "Sara Rosales" in msg
    assert "María" in msg


def test_nps_alto_ofrece_referido(monkeypatch):
    monkeypatch.setattr(storage, "guardar_respuesta_nps", lambda t, p, e="": None)
    monkeypatch.setattr(
        "marca.mensaje_referido_tras_nps_alto",
        lambda tel: "Código INPULSO-ABC123",
    )
    msg = respuesta_seguimiento_nps("523300000001", 10)
    assert "INPULSO" in msg or "Código" in msg


def test_contexto_blog_ansiedad():
    ctx = contexto_blog_si_aplica("tengo mucha ansiedad últimamente")
    assert "blog" in ctx.lower()
    assert contexto_blog_si_aplica("hola qué tal") == ""


def test_mensaje_codigo_referido(monkeypatch):
    monkeypatch.setattr(storage, "obtener_o_crear_codigo_referido", lambda t: "INPULSO-TEST01")
    monkeypatch.setattr(storage, "primer_nombre", lambda t: "Ana")
    msg = mensaje_codigo_referido("523300000001")
    assert "INPULSO-TEST01" in msg
