"""Recibos de pago Inpulso."""
import storage
from recibos import generar_recibo_png


def test_generar_recibo_png_contiene_datos():
    png = generar_recibo_png(
        folio="INP-000042",
        nombre_paciente="María López",
        concepto="Taller Sanando heridas",
        monto=400.0,
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 5000


def test_siguiente_folio_recibo(db_temp):
    f1 = storage.siguiente_folio_recibo()
    f2 = storage.siguiente_folio_recibo()
    assert f1.startswith("INP-")
    assert f1 != f2
