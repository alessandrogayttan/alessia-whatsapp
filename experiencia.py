"""Funciones premium de experiencia del paciente (Tier 1, 2, 4)."""
import datetime
import logging
import re

import pytz
import requests

import config
import storage
from catalogo import _leer_filas_catalogo
from tools import (
    cancelar_cita_paciente,
    consultar_agenda,
    listar_citas_futuras_por_telefono,
)

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)


def calcular_minutos_ruta(telefono: str) -> int | None:
    ubicacion = storage.obtener_ubicacion(telefono)
    if not ubicacion or not config.API_KEY_MAPS:
        return None
    try:
        url = (
            "https://maps.googleapis.com/maps/api/distancematrix/json"
            f"?origins={ubicacion}"
            "&destinations=Av.+Hidalgo+533,Zapopan"
            "&departure_time=now"
            f"&key={config.API_KEY_MAPS}"
        )
        res = requests.get(url, timeout=15).json()
        if res.get("status") != "OK":
            return None
        el = res["rows"][0]["elements"][0]
        if el.get("status") != "OK":
            return None
        dur = el.get("duration_in_traffic", el["duration"])["value"] / 60
        return int(dur) + 5
    except requests.RequestException as e:
        logger.debug("ETA no disponible: %s", e)
        return None


def mensaje_recordatorio_24h(hora_cita: datetime.datetime) -> str:
    hora_txt = hora_cita.strftime("%H:%M")
    return (
        f"🗓️ *Tu cita es mañana*\n\n"
        f"Te esperamos a las {hora_txt} en Inpulso 43.\n\n"
        f"📍 {config.CLINICA_DIRECCION}\n"
        f"🗺️ {config.CLINICA_MAPS_URL}\n\n"
        f"💭 *Check-in:* ¿Cómo te sientes hoy del 1 al 10?\n\n"
        f"📝 *Prep de sesión* (opcional, responde en un mensaje):\n"
        f"1. ¿Hay algo que te gustaría trabajar mañana?\n"
        f"2. ¿Es tu primera sesión con este terapeuta? (sí/no)\n\n"
        f"Si no puedes asistir, avísanos y te ayudamos a reagendar. ✨"
    )


def es_cita_online(event: dict) -> bool:
    texto = (
        (event.get("description") or "")
        + (event.get("summary") or "")
        + (event.get("location") or "")
    ).lower()
    return any(k in texto for k in ("online", "virtual", "zoom", "meet", "videollamada"))


def link_sesion_online(especialista: str = "") -> str:
    esp = especialista.lower()
    for clave, link in config.LINKS_ONLINE_TERAPEUTAS.items():
        if clave in esp and link:
            return link
    return config.LINK_SESION_ONLINE_DEFAULT


def reagendar_cita_inteligente(telefono_paciente: str):
    """Cancela la próxima cita y ofrece hasta 3 horarios alternativos."""
    citas = listar_citas_futuras_por_telefono(telefono_paciente)
    if not citas:
        return (
            "INSTRUCCIÓN PARA LA IA: No hay cita futura para reagendar. "
            "Pregunta amablemente si desea agendar una nueva."
        )

    proxima = citas[0]
    esp = proxima["especialista"]
    detalle_viejo = f"{proxima['fecha']} a las {proxima['hora']} con {esp}"

    resultado_cancel = cancelar_cita_paciente(telefono_paciente)
    if "cancelada exitosamente" not in resultado_cancel.lower() and "ÉXITO" not in resultado_cancel:
        return f"{resultado_cancel} INSTRUCCIÓN: No se pudo reagendar; ofrece ayuda humana."

    opciones = []
    hoy = datetime.datetime.now(ZONA).replace(tzinfo=None)
    for dias in range(8):
        fecha = (hoy + datetime.timedelta(days=dias)).strftime("%Y-%m-%d")
        disp = consultar_agenda(fecha, esp)
        if "Espacios DISPONIBLES" not in disp:
            continue
        parte = disp.split("): ")[1] if "): " in disp else ""
        for hora in parte.split(", ")[:2]:
            hora = hora.strip()
            if hora:
                opciones.append(f"{fecha} a las {hora}")
            if len(opciones) >= 3:
                break
        if len(opciones) >= 3:
            break

    if not opciones:
        return (
            f"INSTRUCCIÓN PARA LA IA: Se canceló la cita del {detalle_viejo} pero no hay "
            f"espacios próximos con {esp}. Ofrece lista de espera con agregar_lista_espera."
        )

    lista = "\n".join(f"• {o}" for o in opciones)
    return (
        f"INSTRUCCIÓN PARA LA IA: Cita cancelada ({detalle_viejo}). "
        f"Ofrece estos horarios alternativos:\n{lista}\n"
        f"Cuando el paciente elija, usa agendar_cita con teléfono {telefono_paciente}."
    )


def guardar_prep_sesion(telefono: str, tema: str, es_primera_sesion: str = "", animo: int = 0):
    """Guarda respuestas de prep de sesión para el terapeuta."""
    event_id = storage.obtener_prep_pendiente(telefono) or ""
    storage.guardar_prep_sesion(telefono, event_id, tema, es_primera_sesion, animo)
    return (
        "ÉXITO: Prep de sesión guardado. INSTRUCCIÓN PARA LA IA: Agradece con calidez; "
        "su terapeuta verá esta información antes de la cita."
    )


def guardar_nota_ritual_cierre(telefono: str, nota: str):
    """Nota privada post-sesión (solo para el paciente, no va al terapeuta)."""
    event_id = storage.obtener_ritual_pendiente(telefono) or ""
    storage.guardar_nota_ritual(telefono, event_id, nota)
    return (
        "ÉXITO: Nota guardada. INSTRUCCIÓN PARA LA IA: Agradece con ternura. "
        "Esta reflexión es privada del paciente."
    )


def texto_prep_para_terapeuta(telefono: str) -> str:
    prep = storage.obtener_prep_sesion_reciente(telefono)
    if not prep:
        return ""
    partes = []
    if prep.get("animo"):
        partes.append(f"Ánimo: {prep['animo']}/10")
    if prep.get("tema"):
        partes.append(f"Tema a trabajar: {prep['tema']}")
    if prep.get("es_primera"):
        partes.append(f"Primera sesión (según paciente): {prep['es_primera']}")
    return "\n".join(partes)


def procesar_aniversarios():
    """Envía mensaje de aniversario terapéutico (1 año desde primera cita)."""
    from whatsapp import enviar_mensaje_whatsapp

    hoy = datetime.datetime.now(ZONA).date()
    for telefono, fecha_str in storage.listar_primeras_citas():
        try:
            primera = datetime.datetime.strptime(fecha_str[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if (hoy - primera).days < 364:
            continue
        anios = hoy.year - primera.year
        if anios < 1:
            continue
        if storage.aniversario_ya_enviado(telefono, anios):
            continue
        msg = (
            f"🌱 *Un año en tu proceso*\n\n"
            f"Hace un año comenzaste tu camino con Inpulso 43. "
            f"Quería reconocer ese paso — cuidarte también es valentía.\n\n"
            f"Si en algún momento quieres platicar, aquí estoy 💙"
        )
        if enviar_mensaje_whatsapp(telefono, msg):
            storage.marcar_aniversario_enviado(telefono, anios)


def procesar_bienvenida_talleres():
    """Sala de espera virtual: bienvenida ~7 días antes del taller."""
    if not config.ID_HOJA_CALCULO:
        return
    from google_client import get_sheets_service
    from whatsapp import enviar_mensaje_whatsapp

    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Inscripciones!A:F"
        ).execute()
        catalogo = {f["nombre"].lower(): f for f in _leer_filas_catalogo()}
        hoy = datetime.datetime.now(ZONA).date()

        for row in result.get("values", [])[1:]:
            if len(row) < 6 or row[5] != "PAGADO":
                continue
            nombre, telefono, taller = row[1], row[2], row[4]
            clave = f"{telefono}|{taller.lower()}"
            if storage.taller_bienvenida_enviada(clave):
                continue
            fila = None
            for nom, data in catalogo.items():
                if taller.lower() in nom or nom in taller.lower():
                    fila = data
                    break
            if not fila or "taller" not in fila.get("tipo", ""):
                continue
            fechas_txt = fila.get("fechas", "")
            if not fechas_txt:
                continue
            nums = re.findall(r"\d{1,2}", fechas_txt)
            if not nums:
                continue
            try:
                dia = int(nums[0])
                mes = hoy.month
                anio = hoy.year
                if dia < hoy.day:
                    mes += 1
                    if mes > 12:
                        mes, anio = 1, anio + 1
                fecha_taller = datetime.date(anio, mes, min(dia, 28))
            except ValueError:
                continue
            dias_falt = (fecha_taller - hoy).days
            if not (5 <= dias_falt <= 8):
                continue
            msg = (
                f"🎉 *Sala de espera — {taller}*\n\n"
                f"¡Hola {nombre}! Tu lugar está confirmado.\n\n"
                f"📅 {fechas_txt}\n"
                f"🕐 {fila.get('horario', '')}\n"
                f"📍 {fila.get('modalidad', 'Presencial')}\n\n"
                f"💡 *Qué traer:* libreta, pluma y mente abierta\n"
                f"🗺️ {config.CLINICA_MAPS_URL}\n\n"
                f"¡Nos vemos pronto! ✨"
            )
            if enviar_mensaje_whatsapp(telefono, msg):
                storage.marcar_taller_bienvenida(clave)
    except Exception as e:
        logger.error("Error bienvenida talleres: %s", e)


def procesar_recordatorios_tareas():
    """Envía recordatorios de tareas terapéuticas asignadas por terapeutas."""
    from whatsapp import enviar_mensaje_whatsapp

    hoy = datetime.datetime.now(ZONA)
    dia_nombre = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][
        hoy.weekday()
    ]
    for tarea in storage.tareas_pendientes_hoy(dia_nombre):
        msg = (
            f"📝 *Recordatorio de tu terapeuta*\n\n"
            f"{tarea['descripcion']}\n\n"
            f"Un paso pequeño también cuenta 🌿"
        )
        if enviar_mensaje_whatsapp(tarea["telefono"], msg):
            storage.marcar_tarea_enviada_hoy(tarea["id"], hoy.strftime("%Y-%m-%d"))
