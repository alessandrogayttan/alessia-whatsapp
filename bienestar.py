"""Contenido de bienestar: frases, trivias, micro-ejercicios, clima."""
import datetime
import logging
import random

import pytz
import requests

import config

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)

FRASES_DIA = [
    "Cuidar de ti no es egoísmo, es necesidad. ✨",
    "Hoy mereces una pausa consciente, aunque sea de un minuto. 🌿",
    "Tu mente también necesita descanso; no tienes que resolverlo todo hoy. 💙",
    "Pedir ayuda es un acto de valentía, no de debilidad. 🙌",
    "Pequeños pasos también cuentan. Lo estás haciendo bien. 😊",
    "Respirar hondo es gratis y siempre está disponible. 🌬️",
    "Eres más resiliente de lo que crees. ✨",
    "Permitirte sentir es parte de sanar. 💜",
]

TRIVIAS = [
    {
        "pregunta": "¿Sabías que respirar 4-7-8 (inhalar 4s, sostener 7s, exhalar 8s) puede calmar el sistema nervioso en minutos?",
        "dato": "Es una técnica usada en terapia para reducir ansiedad aguda.",
    },
    {
        "pregunta": "¿Sabías que escribir 3 cosas por las que agradeces cada día mejora el ánimo en pocas semanas?",
        "dato": "Se llama gratitud orientada y es respaldada por psicología positiva.",
    },
    {
        "pregunta": "¿Sabías que caminar 10 minutos al aire libre puede mejorar tu concentración?",
        "dato": "El movimiento suave libera endorfinas y reduce cortisol.",
    },
    {
        "pregunta": "¿Sabías que hablar de lo que sientes con alguien de confianza reduce la intensidad emocional?",
        "dato": "Nombrar la emoción ('name it to tame it') ayuda al cerebro a regularse.",
    },
]

MICRO_EJERCICIOS = {
    "ansiedad": (
        "🌬️ *Respiración 4-7-8*\n"
        "1. Inhala por la nariz contando hasta 4\n"
        "2. Sostén el aire contando hasta 7\n"
        "3. Exhala lentamente contando hasta 8\n"
        "Repite 3 veces. Estoy aquí contigo."
    ),
    "panico": (
        "🧭 *Grounding 5-4-3-2-1*\n"
        "Nombra: 5 cosas que ves, 4 que tocas, 3 que escuchas, 2 que hueles, 1 que saboreas.\n"
        "Esto ayuda a anclarte al presente."
    ),
    "estres": (
        "💆 *Pausa de 60 segundos*\n"
        "Suelta la mandíbula, baja los hombros, respira lento.\n"
        "Di en voz baja: 'En este momento estoy a salvo.'"
    ),
    "respirar": (
        "🌬️ *Respiración 4-7-8*\n"
        "1. Inhala por la nariz contando hasta 4\n"
        "2. Sostén el aire contando hasta 7\n"
        "3. Exhala lentamente contando hasta 8\n"
        "Repite 3 veces. Estoy aquí contigo."
    ),
    "grounding": (
        "🧭 *Grounding 5-4-3-2-1*\n"
        "Nombra: 5 cosas que ves, 4 que tocas, 3 que escuchas, 2 que hueles, 1 que saboreas.\n"
        "Esto ayuda a anclarte al presente."
    ),
}

MENSAJE_CRISIS = (
    "🆘 *Estoy aquí contigo*\n\n"
    "Si hay riesgo inmediato, llama al *911*.\n"
    "Línea de la Vida (24 h): *800 290 0024*\n\n"
    "Respira conmigo: inhala 4 segundos, exhala 6. "
    "No estás solo/a — el equipo de Inpulso también fue notificado."
)

COMANDOS_BIBLIOTECA = {
    "RESPIRAR": "respirar",
    "GROUNDING": "grounding",
    "CRISIS": "crisis",
}


def comando_biblioteca(texto: str) -> str | None:
    clave = texto.strip().upper()
    if clave == "CRISIS":
        return MENSAJE_CRISIS
    tipo = COMANDOS_BIBLIOTECA.get(clave)
    if tipo and tipo in MICRO_EJERCICIOS:
        return MICRO_EJERCICIOS[tipo]
    return None

RINCON_MUSICAL = {
    "triste": ["Riverside — Agnes Obel", "Holocene — Bon Iver", "Fix You — Coldplay (suave)"],
    "ansioso": ["Weightless — Marconi Union", "Sunset Lover — Petit Biscuit", "Breathe Me — Sia (instrumental)"],
    "feliz": ["Here Comes The Sun — The Beatles", "Good Life — OneRepublic", "Three Little Birds — Bob Marley"],
    "enojado": ["Let It Be — The Beatles", "Human — Rag'n'Bone Man", "Under Pressure — Queen & Bowie"],
    "calma": ["Claire de Lune — Debussy", "Spiegel im Spiegel — Arvo Pärt", "River Flows in You — Yiruma"],
}

MENSAJE_PRIMERA_VEZ = (
    "👋 *¡Bienvenido/a a Inpulso 43!*\n\n"
    "Soy Alessia, tu asistente virtual. Un gusto conocerte.\n\n"
    f"📍 *Ubicación:* {config.CLINICA_DIRECCION}\n"
    f"🗺️ *Mapa:* {config.CLINICA_MAPS_URL}\n"
    "🅿️ *Estacionamiento:* Hay un cajón (sujeto a disponibilidad)\n"
    "⏰ *Llega 10 min antes* de tu cita\n"
    "💡 *Tip:* Piensa qué te gustaría trabajar en sesión\n\n"
    "¿Cómo te llamas? Me encantará ayudarte 😊"
)


def frase_del_dia() -> str:
    dia = datetime.datetime.now(ZONA).toordinal()
    return FRASES_DIA[dia % len(FRASES_DIA)]


def trivia_de_la_semana() -> dict:
    semana = datetime.datetime.now(ZONA).isocalendar()[1]
    return TRIVIAS[semana % len(TRIVIAS)]


def micro_ejercicio_para_texto(texto: str) -> str | None:
    t = texto.lower()
    if any(p in t for p in ("pánico", "panico", "ataque")):
        return MICRO_EJERCICIOS["panico"]
    if any(p in t for p in ("ansios", "ansiedad", "nervios")):
        return MICRO_EJERCICIOS["ansiedad"]
    if any(p in t for p in ("estrés", "estres", "agobiad", "overwhel")):
        return MICRO_EJERCICIOS["estres"]
    return None


def sugerencia_musical(estado: str) -> list[str]:
    e = estado.lower()
    for clave, canciones in RINCON_MUSICAL.items():
        if clave in e:
            return canciones
    return RINCON_MUSICAL["calma"]


def obtener_clima_zapopan() -> str | None:
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={config.CLIMA_LAT}&longitude={config.CLIMA_LON}"
            "&current=precipitation,weather_code,temperature_2m"
            "&timezone=America%2FMexico_City"
        )
        res = requests.get(url, timeout=10).json()
        current = res.get("current", {})
        code = current.get("weather_code", 0)
        temp = current.get("temperature_2m")
        lluvia = current.get("precipitation", 0)
        if code in (51, 53, 55, 61, 63, 65, 80, 81, 82) or (lluvia and lluvia > 0):
            return f"🌧️ Hoy hay lluvia en Zapopan ({temp}°C). Considera salir con anticipación."
        if code in (95, 96, 99):
            return f"⛈️ Hay tormenta en la zona ({temp}°C). Sal con mucho tiempo extra."
        if temp and temp > 32:
            return f"☀️ Hace calor ({temp}°C). Lleva agua y busca sombra al llegar."
    except requests.RequestException as e:
        logger.debug("Clima no disponible: %s", e)
    return None
