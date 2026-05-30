import json
import os
import re
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

# Scheduler: solo un worker/proceso debe ejecutar tareas en segundo plano
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "1").strip().lower() in ("1", "true", "yes")

# WhatsApp — plantillas Meta (fuera de ventana 24 h). Déjalas vacías hasta aprobarlas en Meta.
WHATSAPP_TEMPLATE_24H = os.getenv("WHATSAPP_TEMPLATE_24H", "")
WHATSAPP_TEMPLATE_2H = os.getenv("WHATSAPP_TEMPLATE_2H", "")
WHATSAPP_TEMPLATE_LANG = os.getenv("WHATSAPP_TEMPLATE_LANG", "es_MX")

# Escalación humana — WhatsApp de recepción (opcional, ej. 5233XXXXXXXX)
RECEPCION_WHATSAPP = os.getenv("RECEPCION_WHATSAPP", "")


def _normalizar_whatsapp(numero: str) -> str:
    digits = re.sub(r"\D", "", numero)
    if digits.startswith("521") and len(digits) == 13:
        digits = "52" + digits[3:]
    return digits


def _cargar_terapeutas_whatsapp() -> dict[str, str]:
    """WhatsApp personal de cada terapeuta (52 + 10 dígitos)."""
    base = {
        "sara": _normalizar_whatsapp(os.getenv("WHATSAPP_SARA", "523310265936")),
        "sara rosales": _normalizar_whatsapp(os.getenv("WHATSAPP_SARA", "523310265936")),
        "juan": _normalizar_whatsapp(os.getenv("WHATSAPP_JUAN", "")),
        "patricia": _normalizar_whatsapp(os.getenv("WHATSAPP_PATRICIA", "")),
        "ivan": _normalizar_whatsapp(os.getenv("WHATSAPP_IVAN", "")),
        "iván": _normalizar_whatsapp(os.getenv("WHATSAPP_IVAN", "")),
        "nutricion": _normalizar_whatsapp(os.getenv("WHATSAPP_NUTRICION", "")),
        "nutricionista": _normalizar_whatsapp(os.getenv("WHATSAPP_NUTRICION", "")),
    }
    raw = os.getenv("TERAPEUTAS_WHATSAPP_JSON", "").strip()
    if raw:
        try:
            for nombre, numero in json.loads(raw).items():
                n = _normalizar_whatsapp(str(numero))
                if n:
                    base[nombre.lower()] = n
        except json.JSONDecodeError:
            pass
    return {k: v for k, v in base.items() if v}


TERAPEUTAS_WHATSAPP = _cargar_terapeutas_whatsapp()

TERAPEUTA_NOMBRES = {
    "sara": "Sara Rosales",
    "sara rosales": "Sara Rosales",
    "juan": "Juan",
    "patricia": "Patricia",
    "ivan": "Iván",
    "iván": "Iván",
    "nutricion": "Nutrición",
    "nutricionista": "Nutrición",
}


def identificar_terapeuta(telefono: str) -> str | None:
    """Si el WhatsApp pertenece a un terapeuta registrado, devuelve su nombre."""
    norm = _normalizar_whatsapp(telefono)
    ultimos_10 = norm[-10:] if len(norm) >= 10 else norm
    vistos: set[str] = set()
    for clave, numero in TERAPEUTAS_WHATSAPP.items():
        if not numero or numero in vistos:
            continue
        num10 = numero[-10:] if len(numero) >= 10 else numero
        if numero != norm and num10 != ultimos_10:
            continue
        vistos.add(numero)
        if clave in TERAPEUTA_NOMBRES:
            return TERAPEUTA_NOMBRES[clave]
        return clave.title()
    return None

PALABRAS_LLEGADA = (
    "ya llegué",
    "ya llegue",
    "estoy aquí",
    "estoy aqui",
    "ya estoy aquí",
    "ya estoy aqui",
    "llegué a inpulso",
    "llegue a inpulso",
    "ya estoy en inpulso",
)

PALABRAS_EMERGENCIA = (
    "emergencia",
    "urgencia médica",
    "urgencia medica",
    "suicid",
    "quiero matarme",
    "me quiero matar",
    "voy a hacerme daño",
    "voy a hacerme dano",
    "ataque de pánico grave",
    "ataque de panico grave",
    "no puedo respirar",
    "estoy en peligro",
    "me están golpeando",
    "me estan golpeando",
    "violencia doméstica",
    "violencia domestica",
)

PALABRAS_ANSIEDAD = (
    "ansios", "ansiedad", "pánico", "panico", "nervios", "agobiad", "estres", "estrés",
)

# Seguridad endpoint de diagnóstico (solo producción)
HEALTH_CONFIG_SECRET = os.getenv("HEALTH_CONFIG_SECRET", "")

# Clínica
CLINICA_DIRECCION = "Av. Hidalgo 533, República, 45146 Zapopan, Jal."
CLINICA_MAPS_URL = "https://maps.google.com/?q=Av.+Hidalgo+533,+Zapopan,+Jalisco"
WHATSAPP_MAX_CHARS = 4000
CITAS_CACHE_TTL = int(os.getenv("CITAS_CACHE_TTL", "180"))
PAGO_TOLERANCIA_MXN = float(os.getenv("PAGO_TOLERANCIA_MXN", "10"))
PAGO_TOLERANCIA_PORCENTAJE = float(os.getenv("PAGO_TOLERANCIA_PORCENTAJE", "0.05"))
CLIMA_LAT = 20.7236
CLIMA_LON = -103.3848
REFERIDO_DESCUENTO = "10% en tu siguiente sesión"

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
    "🔒 *Aviso de privacidad*\n"
    "Inpulso 43 usa tus datos (nombre, teléfono y citas) solo para darte atención y "
    "agendar servicios. No los compartimos con terceros ajenos a la clínica.\n"
    "Puedes solicitar la eliminación de tus datos escribiendo *ELIMINAR DATOS*."
)

PALABRAS_PRIVACIDAD = (
    "privacidad",
    "aviso de privacidad",
    "politica de privacidad",
    "política de privacidad",
    "datos personales",
    "proteccion de datos",
    "protección de datos",
)

ZONA_MEXICO = "America/Mexico_City"

# Sesiones online (Tier 4.15) — link por defecto o por terapeuta
LINK_SESION_ONLINE_DEFAULT = os.getenv("LINK_SESION_ONLINE", "")
_links_online_raw = os.getenv("LINKS_ONLINE_TERAPEUTAS_JSON", "").strip()
LINKS_ONLINE_TERAPEUTAS: dict[str, str] = {}
if _links_online_raw:
    try:
        LINKS_ONLINE_TERAPEUTAS = {
            k.lower(): v for k, v in json.loads(_links_online_raw).items() if v
        }
    except json.JSONDecodeError:
        pass


def validar_config_minima():
    """Siempre valida lo mínimo para atender mensajes (local y producción)."""
    requeridas = {
        "TOKEN_WHATSAPP": TOKEN_WHATSAPP,
        "ID_TELEFONO": ID_TELEFONO,
        "GEMINI_API_KEY": GEMINI_API_KEY,
    }
    faltantes = [k for k, v in requeridas.items() if not v]
    if faltantes:
        raise RuntimeError(
            f"Variables de entorno faltantes: {', '.join(faltantes)}. "
            "Configúralas en DigitalOcean > Settings > Environment Variables."
        )
    if not GOOGLE_SERVICE_ACCOUNT_JSON and not Path(SERVICE_ACCOUNT_FILE).is_file():
        raise RuntimeError(
            "Falta GOOGLE_SERVICE_ACCOUNT_JSON o el archivo de cuenta de servicio de Google."
        )


def validar_config_produccion():
    """Validación extra en producción."""
    if not IS_PRODUCTION:
        return
    requeridas = {
        "WHATSAPP_VERIFY_TOKEN": WHATSAPP_VERIFY_TOKEN,
        "ID_HOJA_CALCULO": ID_HOJA_CALCULO,
    }
    faltantes = [k for k, v in requeridas.items() if not v]
    if faltantes:
        raise RuntimeError(
            f"Variables de entorno faltantes en producción: {', '.join(faltantes)}"
        )
