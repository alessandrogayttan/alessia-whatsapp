"""Imagen oficial de formas de pago para WhatsApp."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import config

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
IMAGEN_OFICIAL = ROOT / "assets" / "formas-pago.png"

CAPTION_DEFAULT = (
    "💳 *Formas de pago* Inpulso 43\n"
    "Válidas para talleres, citas presencial y citas en línea.\n"
    "En el concepto pon tu *nombre completo* y envía tu comprobante por aquí 🙏"
)


def bytes_formas_pago() -> bytes | None:
    """Lee la imagen oficial diseñada (PNG)."""
    if not IMAGEN_OFICIAL.is_file():
        logger.error("Falta imagen de formas de pago: %s", IMAGEN_OFICIAL)
        return None
    return IMAGEN_OFICIAL.read_bytes()


def es_consulta_formas_pago(mensaje: str) -> bool:
    """True si el usuario pide cuentas / formas de pago (no comprobante)."""
    n = (mensaje or "").lower()
    n = (
        n.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    if not re.search(
        r"pago|pagar|transferencia|clabe|banorte|banamex|efectivo|"
        r"formas de pago|datos bancarios|cuenta para pagar|como pago|como pago",
        n,
    ):
        return False
    if re.search(r"comprobante|ya pague|envie el pago|confirmar pago", n):
        return False
    return True


def enviar_formas_pago_whatsapp(
    telefono: str,
    caption: str | None = None,
) -> bool:
    """Sube y envía la imagen oficial por WhatsApp."""
    if not telefono:
        return False
    png = bytes_formas_pago()
    if not png:
        return False
    from whatsapp import enviar_imagen_whatsapp

    ok = enviar_imagen_whatsapp(
        telefono,
        png,
        caption=(caption if caption is not None else CAPTION_DEFAULT)[:1024],
        filename="formas-pago.png",
    )
    if ok:
        logger.info("Formas de pago enviadas a %s", telefono[-4:])
    else:
        logger.warning("No se pudo enviar formas de pago a %s", telefono[-4:])
    return ok
