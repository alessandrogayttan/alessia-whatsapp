def test_panel_html_basico(db_temp):
    import storage
    from panel_web import _celda, render_panel_html

    storage.guardar_mensaje_conversacion(
        "wa:5233111", "whatsapp", "user", "hola taller heridas"
    )
    html = render_panel_html()
    assert "Panel Alessia" in html or "Panel analítico Alessia" in html
    assert "taller heridas" in html
    assert 'http-equiv="refresh"' in html
    assert "Interesados en talleres" in html
    assert "pill-ok" in _celda("PAGADO")
    assert "Inpulso 43" in html
