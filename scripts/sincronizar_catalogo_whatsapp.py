"""
Sincroniza talleres de inpulso43.com al catálogo de productos de WhatsApp Business.

Requisitos en Meta (una sola vez):
  1. Commerce Manager → crear catálogo de productos
  2. Vincular catálogo al número de WhatsApp Business
  3. Token con permisos catalog_management y whatsapp_business_management

Variables en .env / DigitalOcean:
  WHATSAPP_CATALOG_ID (opcional si usas WHATSAPP_BUSINESS_ACCOUNT_ID)
  WHATSAPP_BUSINESS_ACCOUNT_ID (WABA ID, no es el Phone Number ID)
  CATALOGO_PRODUCT_IMAGE_URL (opcional, imagen HTTPS por producto)

Uso:
  python scripts/sincronizar_catalogo_whatsapp.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from whatsapp_catalogo import sincronizar_talleres_a_catalogo  # noqa: E402


def main():
    resultado = sincronizar_talleres_a_catalogo(forzar_web=True)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    sys.exit(0 if resultado.get("ok") else 1)


if __name__ == "__main__":
    main()
