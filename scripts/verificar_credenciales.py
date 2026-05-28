"""Valida que las credenciales de .env funcionen correctamente."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import config


def ok(msg):
    print(f"  OK  {msg}")


def fail(msg):
    print(f"  FAIL {msg}")


def main():
    print("Verificando credenciales de Alessia...\n")
    errores = 0

    if not config.TOKEN_WHATSAPP:
        fail("TOKEN_WHATSAPP vacío")
        errores += 1
    else:
        r = requests.get(
            f"https://graph.facebook.com/v19.0/{config.ID_TELEFONO}",
            params={"access_token": config.TOKEN_WHATSAPP},
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            ok(f"WhatsApp conectado — {data.get('verified_name', 'N/A')} ({data.get('status')})")
            webhook = data.get("webhook_configuration", {}).get("application", "")
            if webhook:
                ok(f"Webhook en Meta: {webhook}")
            else:
                fail("Webhook no configurado en Meta")
                errores += 1
        else:
            fail(f"Token WhatsApp inválido: {r.text[:200]}")
            errores += 1

    if not config.GEMINI_API_KEY:
        fail("GEMINI_API_KEY vacío")
        errores += 1
    else:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={config.GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": "ok"}]}]},
            timeout=30,
        )
        if r.status_code == 200:
            ok("Gemini API responde correctamente")
        else:
            fail(f"Gemini API error: {r.text[:200]}")
            errores += 1

    if not config.WHATSAPP_VERIFY_TOKEN:
        fail("WHATSAPP_VERIFY_TOKEN vacío")
        errores += 1
    else:
        ok(f"Verify token configurado ({len(config.WHATSAPP_VERIFY_TOKEN)} chars)")

    if not config.WHATSAPP_APP_SECRET:
        print("  WARN WHATSAPP_APP_SECRET vacío — cópialo de Meta Developers > App > Configuración > Básica")
        print("       https://developers.facebook.com/apps/3817725751857412/settings/basic/")
    else:
        ok("App Secret configurado")

    sa = Path(config.SERVICE_ACCOUNT_FILE)
    if sa.is_file():
        ok(f"Cuenta de servicio Google: {sa.name}")
    else:
        fail(f"No se encontró {config.SERVICE_ACCOUNT_FILE}")
        errores += 1

    if config.ID_HOJA_CALCULO:
        ok(f"Google Sheets ID configurado")
    else:
        fail("ID_HOJA_CALCULO vacío")
        errores += 1

    print()
    if errores:
        print(f"Resultado: {errores} error(es). Corrige .env antes de desplegar.")
        sys.exit(1)
    print("Resultado: credenciales listas (revisa WARN si hay App Secret pendiente).")


if __name__ == "__main__":
    main()
