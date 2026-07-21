"""Cola multimodal durable + consentimiento explícito."""
from google.genai import types

import storage
from cola_contenido import deserializar_contenido, media_id_de_payload, serializar_contenido
from message_queue import encolar_contenido_ia


def test_serializar_deserializar_multimodal(db_temp):
    blob = b"fake-image-bytes"
    partes = [
        types.Part(inline_data=types.Blob(data=blob, mime_type="image/jpeg")),
        types.Part(text="contexto de prueba"),
    ]
    payload, media_id = serializar_contenido(partes)
    assert media_id
    assert media_id_de_payload(payload) == media_id
    recon = deserializar_contenido(payload)
    assert isinstance(recon, list)
    assert any(getattr(p, "text", None) == "contexto de prueba" for p in recon)


def test_encolar_contenido_multimodal_durable(db_temp):
    partes = [
        types.Part(inline_data=types.Blob(data=b"abc", mime_type="image/png")),
        types.Part(text="pago"),
    ]
    msg_id = encolar_contenido_ia("523311111111", partes)
    assert msg_id > 0
    pendientes = storage.obtener_mensajes_pendientes(5)
    assert any(p["id"] == msg_id for p in pendientes)


def test_consentimiento_no_automatico(db_temp):
    assert storage.necesita_consentimiento("523355555555") is True
    assert storage.aviso_privacidad_ya_enviado("523355555555") is False
    storage.marcar_aviso_privacidad_enviado("523355555555")
    assert storage.aviso_privacidad_ya_enviado("523355555555") is True
    assert storage.necesita_consentimiento("523355555555") is True
    storage.registrar_consentimiento("523355555555")
    assert storage.necesita_consentimiento("523355555555") is False


def test_jobs_claim_libera_si_falla(db_temp, monkeypatch):
    import jobs

    llamadas = {"n": 0}

    def fail():
        llamadas["n"] += 1
        return False

    assert jobs._con_claim_recordatorio("e1", "24h", fail) is False
    assert storage.recordatorio_ya_enviado("e1", "24h") is False
    assert llamadas["n"] == 1

    assert jobs._con_claim_recordatorio("e1", "24h", lambda: True) is True
    assert storage.recordatorio_ya_enviado("e1", "24h") is True
    assert jobs._con_claim_recordatorio("e1", "24h", lambda: True) is False
