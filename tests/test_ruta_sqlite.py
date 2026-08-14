from config import ruta_sqlite


def test_ruta_sqlite_produccion_corrige_efimera():
    assert ruta_sqlite("data/alessia.db", produccion=True) == "/data/alessia.db"
    assert ruta_sqlite("/data/alessia.db", produccion=True) == "/data/alessia.db"
    assert ruta_sqlite(None, produccion=False).endswith("alessia.db")
