"""Generación y envío de recibos de pago con marca Inpulso 43."""
from __future__ import annotations

import datetime
import io
import logging
import textwrap
from pathlib import Path

import config
import storage

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
LOGO_PATH = ROOT / "assets" / "inpulso-logo.png"

# Colores marca (logo Inpulso 43)
COLOR_AZUL = "#2563A8"
COLOR_AZUL_OSCURO = "#1E3A5F"
COLOR_ROJO = "#C94C4C"
COLOR_FONDO = "#F4F7FB"
COLOR_BLANCO = "#FFFFFF"
COLOR_TEXTO = "#2D3748"
COLOR_SUAVE = "#64748B"


def _cargar_fuente(tamano: int, negrita: bool = False):
    from PIL import ImageFont

    candidatos = [
        "C:/Windows/Fonts/segoeuib.ttf" if negrita else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if negrita else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if negrita
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for ruta in candidatos:
        if Path(ruta).is_file():
            return ImageFont.truetype(ruta, tamano)
    return ImageFont.load_default()


def generar_recibo_png(
    *,
    folio: str,
    nombre_paciente: str,
    concepto: str,
    monto: float,
    fecha: datetime.datetime | None = None,
) -> bytes:
    """Genera imagen PNG del recibo de pago."""
    from PIL import Image, ImageDraw

    fecha = fecha or datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=-6))
    )
    ancho, alto = 900, 1180
    img = Image.new("RGB", (ancho, alto), COLOR_FONDO)
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, ancho, 200), fill=COLOR_AZUL)
    draw.rectangle((0, 198, ancho, 206), fill=COLOR_ROJO)

    if LOGO_PATH.is_file():
        logo = Image.open(LOGO_PATH).convert("RGBA")
        escala = min(520 / logo.width, 120 / logo.height)
        nw, nh = int(logo.width * escala), int(logo.height * escala)
        logo = logo.resize((nw, nh), Image.Resampling.LANCZOS)
        img.paste(logo, ((ancho - nw) // 2, 36), logo)

    fuente_titulo = _cargar_fuente(34, negrita=True)
    fuente_label = _cargar_fuente(22, negrita=True)
    fuente_valor = _cargar_fuente(24)
    fuente_peq = _cargar_fuente(18)

    card_x1, card_y1, card_x2, card_y2 = 48, 240, ancho - 48, 980
    draw.rounded_rectangle(
        (card_x1, card_y1, card_x2, card_y2), radius=24, fill=COLOR_BLANCO
    )

    titulo = "Recibo de pago"
    tw = draw.textlength(titulo, font=fuente_titulo)
    draw.text(((ancho - tw) / 2, 268), titulo, fill=COLOR_AZUL_OSCURO, font=fuente_titulo)

    campos = [
        ("Folio", folio),
        ("Fecha", fecha.strftime("%d/%m/%Y %H:%M")),
        ("Paciente", nombre_paciente[:60]),
        ("Concepto", concepto[:80]),
        ("Monto pagado", f"${monto:,.2f} MXN"),
        ("Estatus", "PAGADO"),
    ]
    y = 360
    for etiqueta, valor in campos:
        draw.text((card_x1 + 40, y), etiqueta.upper(), fill=COLOR_SUAVE, font=fuente_peq)
        draw.text((card_x1 + 40, y + 28), valor, fill=COLOR_TEXTO, font=fuente_valor)
        y += 88

    draw.line((card_x1 + 40, y, card_x2 - 40, y), fill=COLOR_ROJO, width=2)
    y += 24
    gracias = "Gracias por confiar en Inpulso 43"
    draw.text((card_x1 + 40, y), gracias, fill=COLOR_AZUL, font=fuente_label)

    nota = (
        "Este comprobante confirma la recepción de tu pago. "
        "No sustituye factura fiscal (CFDI). Si necesitas factura, "
        "solicítala por este mismo chat con tus datos fiscales."
    )
    y_nota = 1020
    for linea in textwrap.wrap(nota, width=52):
        draw.text((card_x1 + 40, y_nota), linea, fill=COLOR_SUAVE, font=fuente_peq)
        y_nota += 24

    draw.text(
        (card_x1 + 40, 1120),
        config.CLINICA_DIRECCION,
        fill=COLOR_SUAVE,
        font=fuente_peq,
    )
    draw.text(
        (card_x1 + 40, 1145),
        config.CLINICA_WEB_URL,
        fill=COLOR_AZUL,
        font=fuente_peq,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def enviar_recibo_pago(
    telefono: str,
    nombre_paciente: str,
    concepto: str,
    monto: float,
) -> bool:
    """Genera y envía recibo por WhatsApp. Devuelve True si se envió."""
    if not config.ENABLE_RECIBOS_PAGO:
        return False
    from whatsapp import enviar_imagen_whatsapp

    folio = storage.siguiente_folio_recibo()
    try:
        png = generar_recibo_png(
            folio=folio,
            nombre_paciente=nombre_paciente,
            concepto=concepto,
            monto=monto,
        )
    except Exception as e:
        logger.error("Error generando recibo %s: %s", folio, e)
        return False

    caption = (
        f"✅ Recibo *{folio}* — pago confirmado por ${monto:,.0f} MXN. "
        "Gracias por tu confianza en Inpulso 43 💙"
    )
    ok = enviar_imagen_whatsapp(telefono, png, caption=caption, filename=f"{folio}.png")
    if ok:
        storage.registrar_recibo_enviado(
            folio, telefono, nombre_paciente, concepto, monto
        )
        logger.info("Recibo %s enviado a %s", folio, telefono)
    return ok
