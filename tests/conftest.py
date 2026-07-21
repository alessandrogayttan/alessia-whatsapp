"""Fixtures globales — variables de entorno de prueba ANTES de importar config."""
from __future__ import annotations

import os
import tempfile

# Valores sintéticos (no cuentas reales de producción)
os.environ.setdefault("BANORTE_CLABE", "072320000000000001")
os.environ.setdefault("BANORTE_TARJETA", "4111 1111 1111 1111")
os.environ.setdefault("BANORTE_TITULAR", "Titular Test Banorte")
os.environ.setdefault("BANAMEX_CLABE", "002320000000000001")
os.environ.setdefault("BANAMEX_CUENTA", "7000 00000 01")
os.environ.setdefault("BANAMEX_TITULAR", "Titular Test Banamex")
os.environ.setdefault("EQUIPO_CLAVE_ACCESO", "test-equipo-clave")
os.environ.setdefault("EQUIPO_CLAVE_HASH", "")

import pytest

import config
import storage
from cuentas_pago import obtener_cuentas_oficiales

config.CUENTAS_OFICIALES = obtener_cuentas_oficiales()
config.EQUIPO_CLAVE_ACCESO = os.environ.get("EQUIPO_CLAVE_ACCESO", "test-equipo-clave")
config.EQUIPO_CLAVE_HASH = os.environ.get("EQUIPO_CLAVE_HASH", "").strip()


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
