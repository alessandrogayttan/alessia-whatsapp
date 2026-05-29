"""
Genera un archivo con TODAS las variables para copiar a DigitalOcean.
Uso: python scripts/exportar_vars_do.py
Crea: digitalocean_env.txt (en .gitignore, NO subir a GitHub)
"""
import json
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
env = dotenv_values(ROOT / ".env")
sa_path = ROOT / "agente-inpulso-bda72425fab5.json"
out_path = ROOT / "digitalocean_env.txt"

lines = [
    "VARIABLES PARA DIGITALOCEAN",
    "Copia cada linea KEY = VALUE en Settings > Environment Variables",
    "Marca ENCRYPT en: TOKEN, SECRET, KEY, JSON",
    "=" * 50,
    "",
    f"FLASK_ENV = {env.get('FLASK_ENV', 'production')}",
    f"PORT = {env.get('PORT', '8080')}",
    f"TOKEN_WHATSAPP = {env.get('TOKEN_WHATSAPP', '')}",
    f"ID_TELEFONO = {env.get('ID_TELEFONO', '')}",
    f"META_APP_ID = {env.get('META_APP_ID', '3817725751857412')}",
    f"WHATSAPP_VERIFY_TOKEN = {env.get('WHATSAPP_VERIFY_TOKEN', '')}",
    f"WHATSAPP_APP_SECRET = {env.get('WHATSAPP_APP_SECRET', '')}",
    f"WEBHOOK_CALLBACK_URL = {env.get('WEBHOOK_CALLBACK_URL', '')}",
    f"GEMINI_API_KEY = {env.get('GEMINI_API_KEY', '')}",
    f"ID_HOJA_CALCULO = {env.get('ID_HOJA_CALCULO', '')}",
    f"DATABASE_PATH = {env.get('DATABASE_PATH', 'data/alessia.db')}",
    "",
    "GOOGLE_SERVICE_ACCOUNT_JSON = (pegar JSON completo en una sola linea o multiline en DO)",
    "",
]

if sa_path.is_file():
    sa_minified = json.dumps(json.loads(sa_path.read_text(encoding="utf-8")), separators=(",", ":"))
    lines.append(sa_minified)
else:
    lines.append("ERROR: no se encontro agente-inpulso-bda72425fab5.json")

lines.extend([
    "",
    "=" * 50,
    "RUN COMMAND en DigitalOcean > Settings > Commands:",
    "gunicorn --bind 0.0.0.0:8080 --workers 1 --timeout 120 wsgi:app",
    "",
    "HTTP PORT: 8080",
    "",
    "Despues: Save > Deploy",
    "Verificar: https://alessia-whatsapp-jbems.ondigitalocean.app/health/config",
])

out_path.write_text("\n".join(lines), encoding="utf-8")
print(f"Archivo creado: {out_path}")
print("Abrelo, copia cada variable a DigitalOcean, y redeploy.")
