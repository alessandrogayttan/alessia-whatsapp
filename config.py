import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

FLASK_ENV = os.getenv("FLASK_ENV", "development")
IS_PRODUCTION = FLASK_ENV == "production"

TOKEN_WHATSAPP = os.getenv("TOKEN_WHATSAPP", "")
ID_TELEFONO = os.getenv("ID_TELEFONO", "")
META_APP_ID = os.getenv("META_APP_ID", "3817725751857412")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
WEBHOOK_CALLBACK_URL = os.getenv(
    "WEBHOOK_CALLBACK_URL",
    "https://alessia-whatsapp-jbems.ondigitalocean.app/webhook",
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
API_KEY_MAPS = os.getenv("API_KEY_MAPS", "")
ID_HOJA_CALCULO = os.getenv("ID_HOJA_CALCULO", "")

SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    str(BASE_DIR / "agente-inpulso-bda72425fab5.json"),
)
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "alessia.db"))
PORT = int(os.getenv("PORT", "5000"))

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
]

DIRECTORIO_CALENDARIOS = {
    "juan": "agenda.inpulso43@gmail.com",
    "sara": "q0q97hk07coveikp4fm1938ics@group.calendar.google.com",
    "patricia": "o7tapsufji3t7iuvm6igv7s60s@group.calendar.google.com",
    "ivan": "utguv7r46p04abg3gc0v9b477g@group.calendar.google.com",
    "nutricion": "a9d9c9e14e1e066296439f03995cd509d0e55ea737ec4e1c866040bfb46536db@group.calendar.google.com",
    "mentoras": "0f5b1576668431a17c819c06afb375906b5f045d5256f66cdbd6ecb11665f1c9@group.calendar.google.com",
    "talleres": "8b775cab7bdec4a09023eb859dff073d5b87a38c92d42a80220fd4feed90dada@group.calendar.google.com",
}

CUENTAS_OFICIALES = {
    "BANORTE": {
        "tarjeta": "4189 1430 7739 9932",
        "clabe": "072320003548248000",
        "titular": "Verónica Esmeralda Delgado Andalón",
        "factura": False,
    },
    "BANAMEX": {
        "cuenta": "7009 28855 16",
        "clabe": "002320700928855166",
        "titular": "Inpulso 43",
        "factura": True,
    },
}

AVISO_PRIVACIDAD = (
    "🔒 *Aviso de privacidad*: Al continuar, aceptas que Inpulso 43 procese tus datos "
    "(nombre, teléfono y citas) para brindarte atención. Puedes solicitar la eliminación "
    "de tus datos escribiendo *ELIMINAR DATOS*.\n\n"
)

ZONA_MEXICO = "America/Mexico_City"


def validar_config_produccion():
    """Falla al arrancar si faltan variables críticas en producción."""
    if not IS_PRODUCTION:
        return
    requeridas = {
        "TOKEN_WHATSAPP": TOKEN_WHATSAPP,
        "ID_TELEFONO": ID_TELEFONO,
        "WHATSAPP_VERIFY_TOKEN": WHATSAPP_VERIFY_TOKEN,
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "ID_HOJA_CALCULO": ID_HOJA_CALCULO,
    }
    faltantes = [k for k, v in requeridas.items() if not v]
    if faltantes:
        raise RuntimeError(
            f"Variables de entorno faltantes en producción: {', '.join(faltantes)}"
        )
    if not GOOGLE_SERVICE_ACCOUNT_JSON and not Path(SERVICE_ACCOUNT_FILE).is_file():
        raise RuntimeError(
            "Configura GOOGLE_SERVICE_ACCOUNT_JSON o el archivo "
            f"{SERVICE_ACCOUNT_FILE}"
        )
