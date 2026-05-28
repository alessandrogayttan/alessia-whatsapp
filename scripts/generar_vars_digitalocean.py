"""
Genera la lista de variables de entorno para pegar en DigitalOcean App Platform.
Uso: python scripts/generar_vars_digitalocean.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import dotenv_values

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
SA_PATH = Path(__file__).resolve().parent.parent / "agente-inpulso-bda72425fab5.json"

VARS = [
    ("FLASK_ENV", "production"),
    ("PORT", "8080"),
    ("TOKEN_WHATSAPP", None),
    ("ID_TELEFONO", None),
    ("META_APP_ID", "3817725751857412"),
    ("WHATSAPP_VERIFY_TOKEN", None),
    ("WHATSAPP_APP_SECRET", None),
    ("WEBHOOK_CALLBACK_URL", "https://alessia-whatsapp-jbems.ondigitalocean.app/webhook"),
    ("GEMINI_API_KEY", None),
    ("ID_HOJA_CALCULO", None),
    ("API_KEY_MAPS", ""),
    ("DATABASE_PATH", "data/alessia.db"),
    ("GOOGLE_SERVICE_ACCOUNT_JSON", "__FROM_FILE__"),
]


def main():
    if not ENV_PATH.is_file():
        print(f"No se encontró {ENV_PATH}")
        sys.exit(1)

    env = dotenv_values(ENV_PATH)
    sa_json = ""
    if SA_PATH.is_file():
        sa_json = SA_PATH.read_text(encoding="utf-8")

    print("=" * 60)
    print("VARIABLES PARA DIGITALOCEAN > Settings > App-Level Environment Variables")
    print("=" * 60)
    print()
    print("Run Command (Settings > alessia > Commands):")
    print("  gunicorn --bind 0.0.0.0:8080 --workers 1 --timeout 120 wsgi:app")
    print()
    print("HTTP Port: 8080")
    print()

    for key, default in VARS:
        if key == "GOOGLE_SERVICE_ACCOUNT_JSON":
            value = sa_json
        else:
            value = env.get(key) or default or ""
        if not value and key not in ("API_KEY_MAPS",):
            print(f"  !! FALTA: {key}")
            continue
        if key == "GOOGLE_SERVICE_ACCOUNT_JSON":
            print(f"  {key} = (JSON completo del archivo, {len(value)} chars)")
            print(f"    > En DO elige Encrypt y pega el contenido de agente-inpulso-bda72425fab5.json")
        else:
            masked = value[:6] + "..." if len(value) > 10 and "KEY" in key or "TOKEN" in key or "SECRET" in key else value
            print(f"  {key} = {masked}")

    print()
    print("=" * 60)
    print("Despues de guardar variables > Deploy > Create Deploy / Redeploy")
    print("Verifica: https://alessia-whatsapp-jbems.ondigitalocean.app/health")
    print("=" * 60)


if __name__ == "__main__":
    main()
