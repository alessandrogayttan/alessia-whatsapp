"""Textos de comprobantes / cuentas — una sola fuente para prompts."""
from __future__ import annotations

import config


def texto_cuentas_validas() -> str:
    banorte = config.CUENTAS_OFICIALES["BANORTE"]
    banamex = config.CUENTAS_OFICIALES["BANAMEX"]
    return (
        f"BANORTE CLABE {banorte['clabe']} o BANAMEX CLABE {banamex['clabe']}"
    )


def texto_formas_pago_completas() -> str:
    """Mismas formas de pago para talleres, citas presencial y citas online."""
    banorte = config.CUENTAS_OFICIALES["BANORTE"]
    banamex = config.CUENTAS_OFICIALES["BANAMEX"]
    return (
        "Formas de *pago* en Inpulso 43 (valen para *todo*: talleres, citas presencial y citas en línea) 💳\n"
        "\n"
        "• Efectivo en recepción\n"
        "• Tarjeta (débito/crédito) en recepción\n"
        f"• Transferencia *sin factura* — BANORTE:\n"
        f"  Tarjeta {banorte.get('tarjeta') or '—'} · CLABE {banorte.get('clabe') or '—'} "
        f"a nombre de {banorte.get('titular') or '—'}\n"
        f"• Transferencia *con factura* — BANAMEX:\n"
        f"  Cuenta {banamex.get('cuenta') or '—'} · CLABE {banamex.get('clabe') or '—'} "
        f"a nombre de {banamex.get('titular') or '—'}\n"
        "\n"
        "En el concepto pon tu *nombre completo*. "
        "Las citas *en línea* se pagan completas al confirmar (a más tardar 24 h antes)."
    )


def instruccion_comprobante_pago(*, telefono_paciente: str | None = None) -> str:
    """Compat: delega a media_prompts (instrucciones enriquecidas)."""
    from media_prompts import instruccion_comprobante_pago as _rich

    return _rich(telefono_paciente=telefono_paciente)


def instruccion_comprobante_web() -> str:
    return (
        "[COMPROBANTE DE PAGO — analiza monto, cuenta destino y estatus COMPLETADO. "
        f"Cuentas válidas: {texto_cuentas_validas()}. "
        "Si es válido, llama confirmar_pago_comprobante con el teléfono del paciente "
        "y el monto.]"
    )
