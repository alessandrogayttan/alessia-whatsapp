"""Cuentas de pago oficiales — cargar desde entorno (sin literales en config)."""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def obtener_cuentas_oficiales() -> dict:
    """
    Orden de preferencia:
    1) CUENTAS_OFICIALES_JSON
    2) Variables sueltas BANORTE_* / BANAMEX_*
    """
    raw = os.getenv("CUENTAS_OFICIALES_JSON", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "BANORTE" in data and "BANAMEX" in data:
                return data
            logger.error("CUENTAS_OFICIALES_JSON sin BANORTE/BANAMEX")
        except json.JSONDecodeError as e:
            logger.error("CUENTAS_OFICIALES_JSON inválido: %s", e)

    return {
        "BANORTE": {
            "tarjeta": os.getenv("BANORTE_TARJETA", ""),
            "clabe": os.getenv("BANORTE_CLABE", ""),
            "titular": os.getenv("BANORTE_TITULAR", ""),
            "factura": False,
        },
        "BANAMEX": {
            "cuenta": os.getenv("BANAMEX_CUENTA", ""),
            "clabe": os.getenv("BANAMEX_CLABE", ""),
            "titular": os.getenv("BANAMEX_TITULAR", "Inpulso 43"),
            "factura": True,
        },
    }


def cuentas_completas(cuentas: dict | None = None) -> bool:
    c = cuentas or obtener_cuentas_oficiales()
    return bool(
        c.get("BANORTE", {}).get("clabe") and c.get("BANAMEX", {}).get("clabe")
    )
