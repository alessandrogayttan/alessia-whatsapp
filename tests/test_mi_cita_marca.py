"""Catálogo WhatsApp Business y MI CITA."""
from experiencia import mensaje_mi_cita, respuesta_seguimiento_nps
from marca import contexto_blog_si_aplica
from whatsapp_catalogo import taller_a_item_catalogo


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
    import storage

    monkeypatch.setattr(storage, "primer_nombre", lambda tel: "María")
    msg = mensaje_mi_cita("523300000001")
    assert "Tu próxima cita" in msg
    assert "Sara Rosales" in msg


def test_nps_alto_sin_referido(monkeypatch):
    import storage

    monkeypatch.setattr(storage, "guardar_respuesta_nps", lambda t, p, e="": None)
    msg = respuesta_seguimiento_nps("523300000001", 10)
    assert "gracias" in msg.lower()
    assert "INPULSO" not in msg


def test_contexto_blog_ansiedad():
    ctx = contexto_blog_si_aplica("tengo mucha ansiedad últimamente")
    assert "blog" in ctx.lower()
    assert contexto_blog_si_aplica("hola qué tal") == ""


def test_taller_a_item_catalogo():
    item = taller_a_item_catalogo(
        {
            "id_web": "sanando-heridas",
            "nombre": "Sanando tus heridas del pasado",
            "terapeuta": "Juan y Sara Rosales",
            "fechas": "30 de agosto",
            "horario": "10:00",
            "modalidad": "Presencial",
            "precio": "$400 MXN",
            "temario": "Taller vivencial",
            "cupo": "Lista de espera",
            "url_web": "https://inpulso43.com/talleres.php",
        }
    )
    assert item["id"] == "inpulso-sanando-heridas"
    assert "400.00 MXN" in item["price"]
    assert item["availability"] == "out of stock"
