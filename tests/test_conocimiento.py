"""Tests conocimiento clínico + FAQ."""
import io
from pathlib import Path

import storage
from conocimiento import (
    buscar_conocimiento_clinica,
    es_mime_pdf,
    guardar_conocimiento,
    guardar_conocimiento_desde_pdf,
    listar_conocimiento,
    parece_consulta_informativa,
    registrar_consulta_paciente,
    texto_desde_pdf_bytes,
)


def test_guardar_y_buscar_conocimiento(db_temp):
    msg = guardar_conocimiento(
        "taller heridas",
        "El taller Sanando tus heridas cuesta $2500 y empieza el 15 de agosto.",
        palabras_clave="heridas precio fecha",
        quien="test",
        sync_sheets=False,
    )
    assert "ÉXITO" in msg
    hallado = buscar_conocimiento_clinica("cuánto cuesta el taller de heridas")
    assert "2500" in hallado
    assert "heridas" in hallado.lower()
    listado = listar_conocimiento()
    assert "taller heridas" in listado.lower()


def test_parece_consulta_y_registra_faq(db_temp):
    assert parece_consulta_informativa("¿Cuánto cuesta la sesión?")
    assert not parece_consulta_informativa("ok")
    registrar_consulta_paciente("¿Cuánto cuesta la sesión individual?", "523311111111")
    registrar_consulta_paciente("¿Cuánto cuesta la sesión individual?", "523311111111")
    top = storage.top_preguntas_frecuentes(10)
    assert top
    assert top[0]["veces"] >= 2


def _pdf_bytes_con_texto(texto: str) -> bytes:
    try:
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        y = 800
        for linea in texto.splitlines() or [texto]:
            c.drawString(50, y, linea[:100])
            y -= 14
            if y < 40:
                c.showPage()
                y = 800
        c.save()
        return buf.getvalue()
    except ImportError:
        pass

    stream = f"BT /F1 12 Tf 50 750 Td ({texto[:200]}) Tj ET".encode("latin-1", "replace")
    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode()
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(out.tell())
        out.write(obj)
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return out.getvalue()


def test_es_mime_pdf():
    assert es_mime_pdf("application/pdf")
    assert es_mime_pdf("application/octet-stream", "info.pdf")
    assert not es_mime_pdf("image/jpeg", "foto.jpg")


def test_guardar_conocimiento_desde_pdf(db_temp):
    cuerpo = (
        "SANANDO TUS HERIDAS DEL PASADO\n"
        "Taller presencial 6 de septiembre 2026 en Zapopan.\n"
        "Precio presencial preventa 1000 pesos. Online desde 8 de septiembre."
    )
    pdf = _pdf_bytes_con_texto(cuerpo)
    extraido = texto_desde_pdf_bytes(pdf)
    result = guardar_conocimiento_desde_pdf(
        pdf,
        filename="Sanando tus heridas del pasado.pdf",
        quien="test",
        sync_sheets=False,
    )
    if not extraido or len(extraido) < 40:
        assert result["ok"] is False
        return
    assert result["ok"] is True
    assert result["id"]
    assert "heridas" in (result["tema"] or "").lower()
    hallado = buscar_conocimiento_clinica("precio taller heridas presencial")
    assert "1000" in hallado or "septiembre" in hallado.lower()


def test_guardar_pdf_real_heridas_si_existe(db_temp):
    ruta = Path(r"c:\Users\aless\OneDrive\Desktop\Sanando tus heridas del pasado (1).pdf")
    if not ruta.is_file():
        return
    data = ruta.read_bytes()
    result = guardar_conocimiento_desde_pdf(
        data,
        filename=ruta.name,
        quien="test",
        sync_sheets=False,
    )
    assert result["ok"] is True
    assert result["chars"] > 500
    hallado = buscar_conocimiento_clinica("cuánto cuesta el taller de heridas preventa")
    assert "1000" in hallado or "1200" in hallado
    assert "septiembre" in hallado.lower()
