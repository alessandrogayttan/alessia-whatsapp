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
# Código que Meta muestra al verificar dominio (Configuración → Básica → Dominios)
META_DOMAIN_VERIFICATION_CODE = os.getenv("META_DOMAIN_VERIFICATION_CODE", "")
# Nombre del archivo HTML si Meta lo pide distinto a facebook-domain-verification.html
META_DOMAIN_VERIFICATION_FILE = os.getenv(
    "META_DOMAIN_VERIFICATION_FILE", "facebook-domain-verification.html"
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
API_KEY_MAPS = os.getenv("API_KEY_MAPS", "")
ID_HOJA_CALCULO = os.getenv("ID_HOJA_CALCULO", "")

SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    str(DATA_DIR / "google-service-account.json"),
)
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "alessia.db"))
PORT = int(os.getenv("PORT", "5000"))

# Scheduler: solo un worker/proceso debe ejecutar tareas en segundo plano
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "1").strip().lower() in ("1", "true", "yes")

# Ack inmediato al recibir mensaje (desactivado por defecto; el indicador "escribiendo…" basta)
ENABLE_LAUNCH_ACK = os.getenv("ENABLE_LAUNCH_ACK", "0").strip().lower() in ("1", "true", "yes")
MENSAJE_ACK_PACIENTE = os.getenv(
    "MENSAJE_ACK_PACIENTE",
    "",
)
MENSAJE_ACK_STAFF = os.getenv(
    "MENSAJE_ACK_STAFF",
    "Un momento, ya reviso eso.",
)
WHATSAPP_SEND_RETRIES = int(os.getenv("WHATSAPP_SEND_RETRIES", "3"))

# WhatsApp — plantillas Meta (fuera de ventana 24 h). Déjalas vacías hasta aprobarlas en Meta.
WHATSAPP_TEMPLATE_24H = os.getenv("WHATSAPP_TEMPLATE_24H", "")
WHATSAPP_TEMPLATE_2H = os.getenv("WHATSAPP_TEMPLATE_2H", "")
WHATSAPP_TEMPLATE_LANG = os.getenv("WHATSAPP_TEMPLATE_LANG", "es_MX")
# Quick Reply en plantillas Meta (máx. 25 caracteres; deben coincidir con Meta).
WHATSAPP_BTN_CONFIRMAR_ASISTENCIA = os.getenv(
    "WHATSAPP_BTN_CONFIRMAR_ASISTENCIA", "Confirmo asistencia"
)
WHATSAPP_BTN_REAGENDAR = os.getenv("WHATSAPP_BTN_REAGENDAR", "Necesito reagendar")
# Catálogo de productos WhatsApp (Commerce Manager). WABA ≠ Phone Number ID.
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
WHATSAPP_CATALOG_ID = os.getenv("WHATSAPP_CATALOG_ID", "")
CATALOGO_PRODUCT_IMAGE_URL = os.getenv(
    "CATALOGO_PRODUCT_IMAGE_URL",
    f"{os.getenv('CLINICA_WEB_URL', 'https://inpulso43.com')}/logo.png",
)
ENABLE_RECIBOS_PAGO = os.getenv("ENABLE_RECIBOS_PAGO", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def _normalizar_whatsapp(numero: str) -> str:
    digits = re.sub(r"\D", "", numero)
    if digits.startswith("521") and len(digits) == 13:
        digits = "52" + digits[3:]
    return digits


# Escalación humana — WhatsApp de recepción (52 + 10 dígitos, sin +)
RECEPCION_WHATSAPP = _normalizar_whatsapp(os.getenv("RECEPCION_WHATSAPP", ""))
# Plantilla opcional Meta para avisar a recepción fuera de ventana 24h
WHATSAPP_TEMPLATE_ESCALACION = os.getenv("WHATSAPP_TEMPLATE_ESCALACION", "").strip()
ESCALACION_REAVISO_MINUTOS = int(os.getenv("ESCALACION_REAVISO_MINUTOS", "15"))


def _cargar_terapeutas_whatsapp() -> dict[str, str]:
    """WhatsApp personal de cada terapeuta (52 + 10 dígitos)."""
    base = {
        "sara": _normalizar_whatsapp(os.getenv("WHATSAPP_SARA", "523310265936")),
        "sara rosales": _normalizar_whatsapp(os.getenv("WHATSAPP_SARA", "523310265936")),
        "juan": _normalizar_whatsapp(os.getenv("WHATSAPP_JUAN", "")),
        "juan rosales": _normalizar_whatsapp(os.getenv("WHATSAPP_JUAN", "")),
        "patricia": _normalizar_whatsapp(os.getenv("WHATSAPP_PATRICIA", "")),
        "paty": _normalizar_whatsapp(os.getenv("WHATSAPP_PATRICIA", "")),
        "paty velazquez": _normalizar_whatsapp(os.getenv("WHATSAPP_PATRICIA", "")),
        "patricia velazquez": _normalizar_whatsapp(os.getenv("WHATSAPP_PATRICIA", "")),
        "patricia velázquez": _normalizar_whatsapp(os.getenv("WHATSAPP_PATRICIA", "")),
        "ivan": _normalizar_whatsapp(os.getenv("WHATSAPP_IVAN", "")),
        "iván": _normalizar_whatsapp(os.getenv("WHATSAPP_IVAN", "")),
        "ivan navarro": _normalizar_whatsapp(os.getenv("WHATSAPP_IVAN", "")),
        "iván navarro": _normalizar_whatsapp(os.getenv("WHATSAPP_IVAN", "")),
        "magui": _normalizar_whatsapp(os.getenv("WHATSAPP_MAGUI", "")),
        "magui cardenas": _normalizar_whatsapp(os.getenv("WHATSAPP_MAGUI", "")),
        "magui cárdenas": _normalizar_whatsapp(os.getenv("WHATSAPP_MAGUI", "")),
        "rebeca": _normalizar_whatsapp(os.getenv("WHATSAPP_REBECA", "")),
        "rebeca torres": _normalizar_whatsapp(os.getenv("WHATSAPP_REBECA", "")),
        "betty": _normalizar_whatsapp(os.getenv("WHATSAPP_BETTY", "")),
        "betty martinez": _normalizar_whatsapp(os.getenv("WHATSAPP_BETTY", "")),
        "betty martínez": _normalizar_whatsapp(os.getenv("WHATSAPP_BETTY", "")),
        "nutricion": _normalizar_whatsapp(os.getenv("WHATSAPP_NUTRICION", "")),
        "nutricionista": _normalizar_whatsapp(os.getenv("WHATSAPP_NUTRICION", "")),
        "gabriela": _normalizar_whatsapp(os.getenv("WHATSAPP_NUTRICION", "")),
        "gabriela sanchez": _normalizar_whatsapp(os.getenv("WHATSAPP_NUTRICION", "")),
        "gabriela sánchez": _normalizar_whatsapp(os.getenv("WHATSAPP_NUTRICION", "")),
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
    "juan": "Juan Rosales",
    "juan rosales": "Juan Rosales",
    "patricia": "Paty Velázquez",
    "paty": "Paty Velázquez",
    "paty velazquez": "Paty Velázquez",
    "patricia velazquez": "Paty Velázquez",
    "patricia velázquez": "Paty Velázquez",
    "ivan": "Ivan Navarro",
    "iván": "Ivan Navarro",
    "ivan navarro": "Ivan Navarro",
    "iván navarro": "Ivan Navarro",
    "magui": "Magui Cárdenas",
    "magui cardenas": "Magui Cárdenas",
    "magui cárdenas": "Magui Cárdenas",
    "rebeca": "Rebeca Torres",
    "rebeca torres": "Rebeca Torres",
    "betty": "Betty Martínez",
    "betty martinez": "Betty Martínez",
    "betty martínez": "Betty Martínez",
    "nutricion": "Nutrición",
    "nutricionista": "Nutrición",
    "gabriela": "Gabriela Sánchez",
    "gabriela sanchez": "Gabriela Sánchez",
    "gabriela sánchez": "Gabriela Sánchez",
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


# Modo equipo interno — IA completa para staff (lista blanca por WhatsApp)
ENABLE_MODO_EQUIPO = os.getenv("ENABLE_MODO_EQUIPO", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
EQUIPO_GEMINI_MODEL = os.getenv("EQUIPO_GEMINI_MODEL", "gemini-2.5-flash")
EQUIPO_GEMINI_MODEL_RESPALDO = os.getenv("EQUIPO_GEMINI_MODEL_RESPALDO", "gemini-2.5-flash")
EQUIPO_GEMINI_TEMPERATURE = float(os.getenv("EQUIPO_GEMINI_TEMPERATURE", "0.7"))
EQUIPO_GEMINI_TIMEOUT = int(os.getenv("EQUIPO_GEMINI_TIMEOUT", "120"))
# Preferir EQUIPO_CLAVE_HASH (pbkdf2). EQUIPO_CLAVE_ACCESO solo texto (sin default inseguro).
EQUIPO_CLAVE_HASH = os.getenv("EQUIPO_CLAVE_HASH", "").strip()
EQUIPO_CLAVE_ACCESO = os.getenv("EQUIPO_CLAVE_ACCESO", "").strip()
EQUIPO_SESION_HORAS = int(os.getenv("EQUIPO_SESION_HORAS", "12"))
EQUIPO_CLAVE_MAX_INTENTOS = int(os.getenv("EQUIPO_CLAVE_MAX_INTENTOS", "5"))
EQUIPO_CLAVE_BLOQUEO_MINUTOS = int(os.getenv("EQUIPO_CLAVE_BLOQUEO_MINUTOS", "15"))


def secreto_modo_equipo() -> str:
    """Hash o texto plano configurado para modo equipo."""
    return EQUIPO_CLAVE_HASH or EQUIPO_CLAVE_ACCESO


def _cargar_equipo_inpulso_whatsapp() -> dict[str, str]:
    """WhatsApp personal del equipo interno (modo IA completa)."""
    base: dict[str, str] = {}
    for clave, env_key in (
        ("alessandro", "WHATSAPP_ALESSANDRO"),
        ("recepcion", "RECEPCION_WHATSAPP"),
    ):
        n = _normalizar_whatsapp(os.getenv(env_key, ""))
        if n:
            base[clave] = n
    raw = os.getenv("EQUIPO_INPULSO_WHATSAPP_JSON", "").strip()
    if raw:
        try:
            for nombre, numero in json.loads(raw).items():
                n = _normalizar_whatsapp(str(numero))
                if n:
                    base[str(nombre).lower().strip()] = n
        except json.JSONDecodeError:
            pass
    return {k: v for k, v in base.items() if v}


EQUIPO_INPULSO_WHATSAPP = _cargar_equipo_inpulso_whatsapp()

EQUIPO_NOMBRES = {
    "alessandro": "Alessandro",
    "alessandro gayttan": "Alessandro",
    "recepcion": "Recepción",
}


def identificar_miembro_equipo(telefono: str) -> str | None:
    """Si el WhatsApp está en la lista interna, devuelve nombre (solo para etiqueta, no activa modo)."""
    norm = _normalizar_whatsapp(telefono)
    ultimos_10 = norm[-10:] if len(norm) >= 10 else norm
    vistos: set[str] = set()
    for clave, numero in EQUIPO_INPULSO_WHATSAPP.items():
        if not numero or numero in vistos:
            continue
        num10 = numero[-10:] if len(numero) >= 10 else numero
        if numero != norm and num10 != ultimos_10:
            continue
        vistos.add(numero)
        return EQUIPO_NOMBRES.get(clave, clave.replace("_", " ").title())
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
CLINICA_WEB_URL = os.getenv("CLINICA_WEB_URL", "https://inpulso43.com")
AVISO_PRIVACIDAD_URL = os.getenv(
    "AVISO_PRIVACIDAD_URL",
    f"{CLINICA_WEB_URL}/contacto.php",
)
CLINICA_DIRECCION = "Av. Hidalgo 533, República, 45146 Zapopan, Jal."
CLINICA_MAPS_URL = "https://maps.google.com/?q=Av.+Hidalgo+533,+Zapopan,+Jalisco"
WHATSAPP_MAX_CHARS = 4000
CITAS_CACHE_TTL = int(os.getenv("CITAS_CACHE_TTL", "180"))
CALENDAR_API_RETRIES = int(os.getenv("CALENDAR_API_RETRIES", "4"))
CALENDAR_CONSULTA_REINTENTOS = int(os.getenv("CALENDAR_CONSULTA_REINTENTOS", "3"))
CALENDAR_RETRY_PAUSE_SECONDS = float(os.getenv("CALENDAR_RETRY_PAUSE_SECONDS", "1.5"))
# Tiempo máximo esperando calendario en una conversación (evita colgar WhatsApp)
CALENDAR_MAX_WAIT_SECONDS = float(os.getenv("CALENDAR_MAX_WAIT_SECONDS", "12"))
# Tiempo máximo para keepalive / diagnósticos en segundo plano
CALENDAR_MAX_WAIT_BACKGROUND_SECONDS = float(
    os.getenv("CALENDAR_MAX_WAIT_BACKGROUND_SECONDS", "45")
)
# Calendarios que deben responder en /health/ready (agenda de citas)
CALENDARIOS_CRITICOS = ["sara", "juan", "patricia", "ivan"]
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

from cuentas_pago import obtener_cuentas_oficiales  # noqa: E402

CUENTAS_OFICIALES = obtener_cuentas_oficiales()

AVISO_PRIVACIDAD = (
    "🔒 *Aviso de privacidad*\n"
    "Inpulso 43 usa tus datos (nombre, teléfono y citas) solo para darte atención y "
    "agendar servicios. No los compartimos con terceros ajenos a la clínica.\n"
    f"Más información: {AVISO_PRIVACIDAD_URL}\n"
    "Puedes solicitar la eliminación de tus datos escribiendo *ELIMINAR DATOS*."
)

PALABRAS_ORIENTACION_INICIAL = (
    "no sé qué especialista",
    "no se que especialista",
    "qué especialista necesito",
    "que especialista necesito",
    "no sé a quién",
    "no se a quien",
    "no sé con quién",
    "no se con quien",
    "iniciar un proceso",
    "quiero iniciar un proceso",
    "qué doctor",
    "que doctor",
    "a quien debo ir",
    "a quién debo ir",
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

# Observabilidad y operaciones
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
ALERTA_FALLOS_UMBRAL = int(os.getenv("ALERTA_FALLOS_UMBRAL", "5"))
BACKUP_DIR = os.getenv("BACKUP_DIR", str(DATA_DIR / "backups"))
WEBHOOK_RATE_LIMIT = int(os.getenv("WEBHOOK_RATE_LIMIT", "120"))  # req/min por IP

# Chat web inpulso43.com (canal separado de WhatsApp; desactivado por defecto)
ENABLE_WEB_CHAT = os.getenv("ENABLE_WEB_CHAT", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
WEB_CHAT_RATE_LIMIT = int(os.getenv("WEB_CHAT_RATE_LIMIT", "30"))  # req/min por IP
WEB_CHAT_ORIGINS = tuple(
    o.strip().rstrip("/")
    for o in os.getenv(
        "WEB_CHAT_ORIGINS",
        "https://inpulso43.com,https://www.inpulso43.com,http://localhost:8080",
    ).split(",")
    if o.strip()
)
WHATSAPP_PACIENTES_NUMERO = _normalizar_whatsapp(
    os.getenv("WHATSAPP_PACIENTES_NUMERO", "523324453536")
)
WHATSAPP_PACIENTES_URL = (
    f"https://wa.me/{WHATSAPP_PACIENTES_NUMERO}" if WHATSAPP_PACIENTES_NUMERO else ""
)

# Contenido en vivo de inpulso43.com en cada respuesta
ENABLE_INPULSO_WEB_LIVE = os.getenv("ENABLE_INPULSO_WEB_LIVE", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Historial persistente y RAG del sitio
ENABLE_CONVERSACION_PERSISTENTE = os.getenv("ENABLE_CONVERSACION_PERSISTENTE", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
CONVERSACION_MAX_TURNOS = int(os.getenv("CONVERSACION_MAX_TURNOS", "40"))
ENABLE_INPULSO_RAG = os.getenv("ENABLE_INPULSO_RAG", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
INPULSO_RAG_REINDEX_SECONDS = int(os.getenv("INPULSO_RAG_REINDEX_SECONDS", "21600"))
INPULSO_RAG_PDF_URLS = os.getenv("INPULSO_RAG_PDF_URLS", "").strip()

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


def advertencias_lanzamiento() -> list[str]:
    """Avisos no bloqueantes antes del go-live."""
    avisos = []
    if not WHATSAPP_APP_SECRET:
        avisos.append(
            "WHATSAPP_APP_SECRET vacío: el webhook no valida firmas (riesgo de seguridad)."
        )
    if not WHATSAPP_TEMPLATE_24H:
        avisos.append(
            "WHATSAPP_TEMPLATE_24H vacío: recordatorios 24h pueden fallar fuera de ventana Meta."
        )
    if not WHATSAPP_TEMPLATE_2H:
        avisos.append(
            "WHATSAPP_TEMPLATE_2H vacío: recordatorios 2h pueden fallar fuera de ventana Meta."
        )
    if not RECEPCION_WHATSAPP:
        avisos.append("RECEPCION_WHATSAPP vacío: escalaciones HABLAR CON PERSONA sin destino.")
    if not API_KEY_MAPS:
        avisos.append("API_KEY_MAPS vacío: sin ETA/tráfico en recordatorios.")
    if not LINK_SESION_ONLINE_DEFAULT and not LINKS_ONLINE_TERAPEUTAS:
        avisos.append("LINK_SESION_ONLINE vacío: sesiones online sin link automático.")
    if IS_PRODUCTION and not HEALTH_CONFIG_SECRET:
        avisos.append("HEALTH_CONFIG_SECRET vacío: /health/config queda deshabilitado.")
    staff_requerido = {
        "sara": os.getenv("WHATSAPP_SARA", "523310265936"),
        "juan": os.getenv("WHATSAPP_JUAN", ""),
        "paty": os.getenv("WHATSAPP_PATRICIA", ""),
        "ivan": os.getenv("WHATSAPP_IVAN", ""),
        "magui": os.getenv("WHATSAPP_MAGUI", ""),
        "rebeca": os.getenv("WHATSAPP_REBECA", ""),
        "betty": os.getenv("WHATSAPP_BETTY", ""),
        "nutricion": os.getenv("WHATSAPP_NUTRICION", ""),
    }
    terapeutas_sin_numero = [
        nombre for nombre, numero in staff_requerido.items()
        if not _normalizar_whatsapp(numero)
    ]
    if terapeutas_sin_numero:
        avisos.append(
            f"WhatsApp de terapeutas sin configurar: {', '.join(terapeutas_sin_numero)}"
        )
    return avisos


def validar_config_produccion():
    """Validación extra en producción (fail-closed)."""
    if not IS_PRODUCTION:
        return
    from cuentas_pago import cuentas_completas

    requeridas = {
        "WHATSAPP_VERIFY_TOKEN": WHATSAPP_VERIFY_TOKEN,
        "WHATSAPP_APP_SECRET": WHATSAPP_APP_SECRET,
        "ID_HOJA_CALCULO": ID_HOJA_CALCULO,
        "HEALTH_CONFIG_SECRET": HEALTH_CONFIG_SECRET,
        "RECEPCION_WHATSAPP": RECEPCION_WHATSAPP,
    }
    faltantes = [k for k, v in requeridas.items() if not v]
    if ENABLE_MODO_EQUIPO and not secreto_modo_equipo():
        faltantes.append("EQUIPO_CLAVE_HASH|EQUIPO_CLAVE_ACCESO")
    if not cuentas_completas(CUENTAS_OFICIALES):
        faltantes.append("CUENTAS_OFICIALES_JSON|BANORTE_CLABE+BANAMEX_CLABE")
    if faltantes:
        raise RuntimeError(
            f"Variables de entorno faltantes en producción: {', '.join(faltantes)}"
        )
    for aviso in advertencias_lanzamiento():
        import logging

        logging.getLogger(__name__).warning("Lanzamiento: %s", aviso)
