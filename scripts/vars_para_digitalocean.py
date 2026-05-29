"""
Imprime variables listas para copiar en DigitalOcean (sin mostrar valores completos).
Ejecutar: python scripts/vars_para_digitalocean.py
"""
import json
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
env = dotenv_values(ROOT / ".env")
sa_file = ROOT / "agente-inpulso-bda72425fab5.json"

REQUIRED = [
    "FLASK_ENV",
    "PORT",
    "TOKEN_WHATSAPP",
    "ID_TELEFONO",
    "META_APP_ID",
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_APP_SECRET",
    "WEBHOOK_CALLBACK_URL",
    "GEMINI_API_KEY",
    "ID_HOJA_CALCULO",
    "DATABASE_PATH",
]

print("\n=== CHECKLIST DIGITALOCEAN ===\n")
print("DigitalOcean > tu app > Settings > Environment Variables\n")

faltan = []
for key in REQUIRED:
    val = env.get(key, "")
    if key == "FLASK_ENV" and not val:
        val = "production"
    if key == "PORT" and not val:
        val = "8080"
    if val:
        show = val if len(val) < 20 else val[:8] + "..." + val[-4:]
        if "TOKEN" in key or "SECRET" in key or "KEY" in key:
            show = f"({len(val)} caracteres — ENCRYPT en DO)"
        print(f"  [x] {key} = {show}")
    else:
        print(f"  [ ] {key}  <-- FALTA en tu .env local")
        faltan.append(key)

if sa_file.is_file():
    print(f"  [x] GOOGLE_SERVICE_ACCOUNT_JSON = ({sa_file.stat().st_size} bytes — pegar JSON en DO, ENCRYPT)")
else:
    print("  [ ] GOOGLE_SERVICE_ACCOUNT_JSON  <-- falta archivo JSON")
    faltan.append("GOOGLE_SERVICE_ACCOUNT_JSON")

print("\nRun command en DO:")
print("  gunicorn --bind 0.0.0.0:8080 --workers 1 --timeout 120 wsgi:app")
print("\nHTTP Port: 8080")
print("\nDespues de pegar variables: Save > Deploy\n")

if faltan:
    print("ATENCION: completa tu .env local primero:", ", ".join(faltan))
    sys.exit(1)

print("Todo listo en .env local. Copia cada valor a DigitalOcean y redeploy.")
