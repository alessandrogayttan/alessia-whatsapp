import hashlib
import hmac
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import dotenv_values

env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
base = "https://alessia-whatsapp-jbems.ondigitalocean.app"
secret = env.get("WHATSAPP_APP_SECRET", "")
verify = env.get("WHATSAPP_VERIFY_TOKEN", "")

print("=== Diagnostico produccion ===\n")

r = requests.get(f"{base}/health", timeout=15)
print(f"health: {r.status_code} {r.text}")

r = requests.get(
    f"{base}/webhook",
    params={"hub.mode": "subscribe", "hub.verify_token": verify, "hub.challenge": "test123"},
    timeout=15,
)
print(f"GET verify (token local): {r.status_code} {r.text[:80]}")

body = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "messages": [
                            {
                                "id": "diag_script_001",
                                "from": "523326505999",
                                "type": "text",
                                "text": {"body": "hola diagnostico"},
                            }
                        ],
                        "metadata": {"phone_number_id": "1090957250773198"},
                    }
                }
            ]
        }
    ],
}
payload = json.dumps(body).encode()
sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

r = requests.post(
    f"{base}/webhook",
    data=payload,
    headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    timeout=15,
)
print(f"POST con firma Meta: {r.status_code} {r.text}")

r = requests.post(
    f"{base}/webhook",
    data=payload,
    headers={"Content-Type": "application/json"},
    timeout=15,
)
print(f"POST sin firma: {r.status_code} {r.text}")
