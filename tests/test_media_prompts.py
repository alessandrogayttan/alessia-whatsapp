def test_normalizar_mime_whatsapp():
    from media_prompts import normalizar_mime_media

    assert normalizar_mime_media("audio/ogg; codecs=opus", "voice") == "audio/ogg"
    assert normalizar_mime_media("image/jpeg", "image") == "image/jpeg"
    assert normalizar_mime_media(None, "voice") == "audio/ogg"


def test_instruccion_voz_obliga_transcribir():
    from media_prompts import instruccion_voz

    t = instruccion_voz().lower()
    assert "transcribe" in t or "transcribir" in t
    assert "no digas" in t


def test_instruccion_comprobante_obliga_herramienta():
    from media_prompts import instruccion_comprobante_pago

    t = instruccion_comprobante_pago(telefono_paciente="523311111111")
    assert "confirmar_pago_comprobante" in t
    assert "523311111111" in t
    assert "OBLIGATORIO" in t


def test_instruccion_media_paciente_imagen_incluye_pago():
    from media_prompts import instruccion_media_paciente

    t = instruccion_media_paciente(
        tipo_mensaje="image", caption="aquí va el pago", telefono="5233111"
    )
    assert "COMPROBANTE" in t
    assert "aquí va el pago" in t
