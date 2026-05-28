"""
Registra o actualiza el webhook de WhatsApp en Meta.
Requiere WHATSAPP_APP_SECRET en .env (Meta Developers > Configuración > Básica).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import config

APP_ID = config.META_APP_ID if hasattr(config, "META_APP_ID") else "3817725751857412"
CALLBACK = getattr(config, "WEBHOOK_CALLBACK_URL", None) or "https://alessia-whatsapp-jbems.ondigitalocean.app/webhook"


def main():
    if not config.WHATSAPP_APP_SECRET:
        print("Falta WHATSAPP_APP_SECRET en .env")
        print("1. Abre: https://developers.facebook.com/apps/3817725751857412/settings/basic/")
        print("2. Copia 'Clave secreta de la app' y pégala en .env como WHATSAPP_APP_SECRET=...")
        print("3. Vuelve a ejecutar: python scripts/configurar_webhook_meta.py")
        sys.exit(1)

    app_token = f"{APP_ID}|{config.WHATSAPP_APP_SECRET}"
    url = f"https://graph.facebook.com/v19.0/{APP_ID}/subscriptions"

    payload = {
        "object": "whatsapp_business_account",
        "callback_url": CALLBACK,
        "verify_token": config.WHATSAPP_VERIFY_TOKEN,
        "fields": "messages",
        "access_token": app_token,
    }

    print(f"Configurando webhook en Meta...")
    print(f"  URL:    {CALLBACK}")
    print(f"  Token:  {config.WHATSAPP_VERIFY_TOKEN}")

    r = requests.post(url, data=payload, timeout=30)
    if r.status_code == 200:
        print("Webhook registrado correctamente en Meta.")
        _verificar_callback()
        return

    print(f"Error {r.status_code}: {r.text}")
    sys.exit(1)


def _verificar_callback():
    test_url = CALLBACK
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": config.WHATSAPP_VERIFY_TOKEN,
        "hub.challenge": "alessia_test_ok",
    }
    r = requests.get(test_url, params=params, timeout=30)
    if r.status_code == 200 and r.text.strip() == "alessia_test_ok":
        print("Verificación GET del servidor: OK")
    else:
        print(
            f"WARN: Meta aceptó el webhook pero tu servidor respondió {r.status_code}: {r.text[:100]}"
        )
        print("      Despliega el código nuevo en DigitalOcean antes de que Meta envíe mensajes.")


if __name__ == "__main__":
    main()
