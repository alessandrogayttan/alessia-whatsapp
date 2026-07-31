"""Tests cola durable de sync Modo Pro."""
import storage


def test_encolar_y_procesar_trabajo_analytics(monkeypatch, db_temp):
    storage.init_db()
    avisos = []

    monkeypatch.setattr(
        "trabajos_pesados._avisar_whatsapp",
        lambda tel, msg: avisos.append((tel, msg)),
    )
    monkeypatch.setattr(
        "analytics.sincronizar_panel_analytics",
        lambda: "ÉXITO: Analytics ok",
    )

    from trabajos_pesados import (
        encolar_sync_analytics,
        procesar_un_trabajo,
        responder_estado_trabajo,
    )

    tel = "5233123456789"
    storage.activar_sesion_equipo(tel, "Alessandro", 12)
    job_id = encolar_sync_analytics(tel)
    assert job_id > 0
    assert "proceso" in (responder_estado_trabajo(tel) or "").lower()

    assert procesar_un_trabajo() is True
    job = storage.ultimo_trabajo_telefono(tel)
    assert job["estado"] == "ok"
    assert avisos and "ÉXITO" in avisos[0][1]
    assert "listo" in (responder_estado_trabajo(tel) or "").lower()


def test_no_duplica_trabajo_pendiente(db_temp):
    storage.init_db()
    tel = "523399999999"
    a = storage.encolar_trabajo_pesado("sync_analytics", tel)
    b = storage.encolar_trabajo_pesado("sync_analytics", tel)
    assert a == b
