"""Sync automático de hojas (sin WhatsApp)."""
import os


def test_sync_auto_minuto_ejecuta_ligero(monkeypatch, db_temp):
    monkeypatch.setenv("SYNC_HOJAS_AUTO_MINUTO", "1")
    import config

    monkeypatch.setattr(config, "ID_HOJA_CALCULO", "sheet-test")

    llamados = []

    monkeypatch.setattr(
        "heridas_sheet.sincronizar_heridas_datos",
        lambda: llamados.append("heridas") or {"inscritos": 1, "interesados": 2},
    )
    monkeypatch.setattr(
        "analytics.actualizar_analytics",
        lambda **kwargs: llamados.append(("analytics", kwargs)) or "https://sheet",
    )

    from jobs import sincronizar_hojas_auto_minuto_background

    sincronizar_hojas_auto_minuto_background()
    assert "heridas" in llamados
    assert any(c[0] == "analytics" for c in llamados if isinstance(c, tuple))
    assert llamados[-1][1].get("con_grafico") is True


def test_sync_auto_minuto_off_por_defecto(monkeypatch, db_temp):
    monkeypatch.setenv("SYNC_HOJAS_AUTO_MINUTO", "0")
    llamados = []
    monkeypatch.setattr(
        "heridas_sheet.sincronizar_heridas_datos",
        lambda: llamados.append(1),
    )
    from jobs import sincronizar_hojas_auto_minuto_background

    sincronizar_hojas_auto_minuto_background()
    assert llamados == []
