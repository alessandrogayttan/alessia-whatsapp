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
    prefijo = "[COMPROBANTE DE PAGO"
    if telefono_paciente:
        prefijo += f" — teléfono paciente: {telefono_paciente}"
    return (
        f"{prefijo}]. "
        "Analiza internamente: monto numérico, cuenta destino, estatus COMPLETADO. "
        f"Cuentas válidas: {texto_cuentas_validas()}. "
        "OBLIGATORIO: llama confirmar_pago_comprobante con el monto. "
        "Al paciente NO le digas que hay confirmación automática por IA."
    )


def instruccion_comprobante_web() -> str:
    return (
        "[COMPROBANTE DE PAGO — analiza monto, cuenta destino y estatus COMPLETADO. "
        f"Cuentas válidas: {texto_cuentas_validas()}. "
        "Si es válido, llama confirmar_pago_comprobante con el teléfono del paciente "
        "y el monto.]"
    )
