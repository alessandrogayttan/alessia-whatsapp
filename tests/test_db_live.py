def test_base_operativa_vacia(db_temp):
    import storage

    assert storage.base_operativa_vacia() is True
    storage.guardar_mensaje_conversacion("wa:1", "whatsapp", "user", "hola")
    assert storage.base_operativa_vacia() is False


def test_restaurar_sin_s3_no_hace_nada(db_temp, monkeypatch):
    import db_backup

    monkeypatch.setattr(db_backup, "_s3_listo", lambda: False)
    assert db_backup.restaurar_sqlite_live_si_vacia() is False
