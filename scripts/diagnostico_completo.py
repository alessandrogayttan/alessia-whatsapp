"""Diagnostico completo: local + produccion + envio WhatsApp."""
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
env = dotenv_values(ROOT / ".env")
BASE = "https://alessia-whatsapp-jbems.ondigitalocean.app"

token = env.get("TOKEN_WHATSAPP", "")
phone_id = env.get("ID_TELEFONO", "")
secret = env.get("WHATSAPP_APP_SECRET", "")
verify = env.get("WHATSAPP_VERIFY_TOKEN", "")
gemini = env.get("GEMINI_API_KEY", "")
test_num = env.get("PRUEBA_NUMERO", "523326505999")

print("=" * 60)
print("DIAGNOSTICO COMPLETO ALESSIA")
print("=" * 60)

# 1 Meta token
print("\n[1] Token WhatsApp (Meta API)")
r = requests.get(
    f"https://graph.facebook.com/v19.0/{phone_id}",
    params={"fields": "display_phone_number,verified_name,status,quality_rating", "access_token": token},
    timeout=30,
)
if r.status_code == 200:
    d = r.json()
    print(f"  OK  Numero: {d.get('display_phone_number')} | Estado: {d.get('status')}")
else:
    print(f"  FAIL {r.status_code}: {r.text[:300]}")

# 2 Enviar mensaje directo (sin webhook)
print("\n[2] Envio directo WhatsApp API -> tu celular")
msg = "Diagnostico Alessia: si recibes esto, el TOKEN_WHATSAPP funciona."
r = requests.post(
    f"https://graph.facebook.com/v19.0/{phone_id}/messages",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={"messaging_product": "whatsapp", "to": test_num, "type": "text", "text": {"body": msg}},
    timeout=30,
)
if r.status_code == 200:
    print(f"  OK  Mensaje enviado a {test_num}. Revisa tu WhatsApp.")
else:
    print(f"  FAIL {r.status_code}: {r.text[:400]}")

# 3 Gemini
print("\n[3] Gemini API")
r = requests.post(
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini}",
    json={"contents": [{"parts": [{"text": "Di hola en una palabra"}]}]},
    timeout=30,
)
print(f"  {'OK' if r.status_code == 200 else 'FAIL'}  {r.status_code}")

# 4 Produccion health
print("\n[4] Servidor DigitalOcean")
r = requests.get(f"{BASE}/health", timeout=15)
print(f"  {'OK' if r.status_code == 200 else 'FAIL'}  /health -> {r.text}")

# 5 Verify token en produccion
print("\n[5] WHATSAPP_VERIFY_TOKEN en DigitalOcean")
r = requests.get(
    f"{BASE}/webhook",
    params={"hub.mode": "subscribe", "hub.verify_token": verify, "hub.challenge": "DIAG_OK"},
    timeout=15,
)
if r.status_code == 200 and r.text.strip() == "DIAG_OK":
    print(f"  OK  Verify token coincide: {verify}")
else:
    print(f"  FAIL  Produccion respondio {r.status_code} (esperaba DIAG_OK)")
    print(f"        Tu .env local tiene: {verify}")
    print("        => DigitalOcean NO tiene WHATSAPP_VERIFY_TOKEN configurado igual")

# 6 App secret en produccion
print("\n[6] WHATSAPP_APP_SECRET en DigitalOcean")
body = {
    "object": "whatsapp_business_account",
    "entry": [{"changes": [{"value": {"messages": [{"id": f"diag_{int(time.time())}", "from": test_num, "type": "text", "text": {"body": "test prod"}}], "metadata": {"phone_number_id": phone_id}}}]}],
}
payload = json.dumps(body).encode()
sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
r_signed = requests.post(f"{BASE}/webhook", data=payload, headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig}, timeout=15)
r_unsigned = requests.post(f"{BASE}/webhook", data=payload, headers={"Content-Type": "application/json"}, timeout=15)
if r_unsigned.status_code == 403:
    print("  OK  App Secret configurado (POST sin firma rechazado)")
elif r_signed.status_code == 200 and r_unsigned.status_code == 200:
    print("  WARN App Secret NO configurado en DO (acepta POST sin firma)")
else:
    print(f"  INFO signed={r_signed.status_code} unsigned={r_unsigned.status_code}")

# 7 Google JSON local
print("\n[7] Google Service Account")
sa = ROOT / "agente-inpulso-bda72425fab5.json"
print(f"  {'OK' if sa.is_file() else 'FAIL'}  archivo local: {sa.name}")

print("\n" + "=" * 60)
print("FIN. Revisa si llego el mensaje de prueba [2] a tu WhatsApp.")
print("=" * 60)
