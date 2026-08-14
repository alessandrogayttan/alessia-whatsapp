from pathlib import Path

from config import ruta_sqlite


def test_ruta_sqlite_preferida_sin_comprobar():
    assert ruta_sqlite("data/alessia.db", produccion=True, comprobar=False) == "/data/alessia.db"
    assert ruta_sqlite("/data/alessia.db", produccion=True, comprobar=False) == "/data/alessia.db"
    assert ruta_sqlite(None, produccion=False, comprobar=False).endswith("alessia.db")


def test_ruta_sqlite_cae_si_no_puede_escribir_data(monkeypatch, tmp_path):
    import config as cfg

    def fake(parent: Path) -> bool:
        try:
            return parent.resolve() == tmp_path.resolve()
        except OSError:
            return False

    monkeypatch.setattr(cfg, "directorio_escribible", fake)
    assert (
        cfg.ruta_sqlite("/data/alessia.db", produccion=True, data_dir=tmp_path)
        == str(tmp_path / "alessia.db")
    )
