import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN_WHATSAPP")
ID_TELEFONO = os.getenv("ID_TELEFONO")
TU_NUMERO = os.getenv("PRUEBA_NUMERO", "")

if not TOKEN or not ID_TELEFONO:
    print("Configura TOKEN_WHATSAPP e ID_TELEFONO en tu archivo .env")
    sys.exit(1)

if not TU_NUMERO:
    print("Configura PRUEBA_NUMERO en .env (ej: 523312345678)")
    sys.exit(1)

url = f"https://graph.facebook.com/v19.0/{ID_TELEFONO}/messages"
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}
data = {
    "messaging_product": "whatsapp",
    "to": TU_NUMERO,
    "type": "template",
    "template": {
        "name": "hello_world",
        "language": {"code": "en_US"},
    },
}

print("Enviando mensaje de prueba...")
respuesta = requests.post(url, headers=headers, data=json.dumps(data), timeout=30)

if respuesta.status_code == 200:
    print("Éxito. Revisa tu celular.")
else:
    print(f"Error {respuesta.status_code}:")
    print(respuesta.text)
