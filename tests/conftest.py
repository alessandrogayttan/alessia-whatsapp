import os
import tempfile

import pytest

import config
import storage


@pytest.fixture
def db_temp(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(config, "DATABASE_PATH", path)
    storage.init_db()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass
