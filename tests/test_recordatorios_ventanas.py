"""Ventanas y parsing de recordatorios de citas."""
import datetime

from jobs import (
    _extraer_telefono_evento,
    _sanear_param_plantilla,
    tipo_recordatorio_por_diferencia,
)


def test_ventana_24h_amplia():
    assert tipo_recordatorio_por_diferencia(datetime.timedelta(hours=24)) == "24h"
    assert tipo_recordatorio_por_diferencia(datetime.timedelta(hours=22)) == "24h"
    assert tipo_recordatorio_por_diferencia(datetime.timedelta(hours=25, minutes=30)) == "24h"
    assert tipo_recordatorio_por_diferencia(datetime.timedelta(hours=18)) is None


def test_ventana_2h_amplia():
    assert tipo_recordatorio_por_diferencia(datetime.timedelta(hours=2)) == "2h"
    assert tipo_recordatorio_por_diferencia(datetime.timedelta(minutes=100)) == "2h"
    assert tipo_recordatorio_por_diferencia(datetime.timedelta(minutes=140)) == "2h"
    assert tipo_recordatorio_por_diferencia(datetime.timedelta(minutes=60)) is None


def test_extraer_telefono_evento():
    assert (
        _extraer_telefono_evento("Cita de consulta. Teléfono: 523312345678")
        == "523312345678"
    )
    assert (
        _extraer_telefono_evento("Cita ONLINE. Telefono: 33 1234 5678")
        == "523312345678"
    )
    assert _extraer_telefono_evento("Sin dato de contacto") is None


def test_sanear_param_plantilla():
    assert _sanear_param_plantilla("Ana\nMaría") == "Ana María"
    assert _sanear_param_plantilla("") == "hola"
