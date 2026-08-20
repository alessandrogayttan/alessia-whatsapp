"""Textos de comprobantes / cuentas — una sola fuente para prompts."""
from __future__ import annotations

import config


def texto_cuentas_validas() -> str:
    banorte = config.CUENTAS_OFICIALES["BANORTE"]
    banamex = config.CUENTAS_OFICIALES["BANAMEX"]
    return (
        f"BANORTE CLABE {banorte['clabe']} o BANAMEX CLABE {banamex['clabe']}"
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
