import datetime
import logging
import re

import pytz
import requests

import config
import storage
from google_client import get_calendar_service, get_sheets_service
from tools import consultar_agenda
from whatsapp import enviar_mensaje_whatsapp

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)


def limpiar_inscripciones_pendientes_background():
    if not config.ID_HOJA_CALCULO:
        return
    try:
        service = get_sheets_service()
        sheet_metadata = service.spreadsheets().get(
            spreadsheetId=config.ID_HOJA_CALCULO
        ).execute()
        sheet_id_inscripciones = None
        for s in sheet_metadata.get("sheets", []):
            if s.get("properties", {}).get("title") == "Inscripciones":
                sheet_id_inscripciones = s.get("properties", {}).get("sheetId")
                break
        if sheet_id_inscripciones is None:
            return

        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Inscripciones!A:F"
        ).execute()
        rows = result.get("values", [])
        ahora = datetime.datetime.now(ZONA)

        for i in range(len(rows) - 1, 0, -1):
            row = rows[i]
            if len(row) >= 6 and row[5] == "PENDIENTE":
                try:
                    fecha_reg = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                    fecha_reg = ZONA.localize(fecha_reg)
                    if ahora - fecha_reg > datetime.timedelta(hours=24):
                        body = {
                            "requests": [
                                {
                                    "deleteDimension": {
                                        "range": {
                                            "sheetId": sheet_id_inscripciones,
                                            "dimension": "ROWS",
                                            "startIndex": i,
                                            "endIndex": i + 1,
                                        }
                                    }
                                }
                            ]
                        }
                        service.spreadsheets().batchUpdate(
                            spreadsheetId=config.ID_HOJA_CALCULO, body=body
                        ).execute()
                        logger.info("Inscripción eliminada por falta de pago: %s", row[1])
                except ValueError:
                    continue
    except Exception as e:
        logger.error("Error limpieza inscripciones: %s", e)


def _enviar_recordatorio_24h(telefono: str, hora_cita: datetime.datetime, event_id: str):
    if storage.recordatorio_ya_enviado(event_id, "24h"):
        return
    msg = (
        f"🗓️ *Confirmación de Cita*\n\n¡Hola! Te escribimos de Inpulso 43 para confirmar "
        f"tu cita de mañana a las {hora_cita.strftime('%H:%M')}. \n\n"
        f"¿Podrías confirmarnos tu asistencia respondiendo a este mensaje? En caso de no "
        f"poder asistir, te agradecemos mucho que nos avises para poder cederle el espacio "
        f"a otro paciente en lista de espera. ✨"
    )
    if enviar_mensaje_whatsapp(telefono, msg):
        storage.marcar_recordatorio_enviado(event_id, "24h")


def _enviar_recordatorio_2h(telefono: str, hora_cita: datetime.datetime, event_id: str):
    if storage.recordatorio_ya_enviado(event_id, "2h"):
        return

    ubicacion = storage.obtener_ubicacion(telefono)
    if ubicacion and config.API_KEY_MAPS:
        try:
            url = (
                "https://maps.googleapis.com/maps/api/distancematrix/json"
                f"?origins={ubicacion}"
                "&destinations=Av.+Hidalgo+533,Zapopan"
                "&departure_time=now"
                f"&key={config.API_KEY_MAPS}"
            )
            res = requests.get(url, timeout=15).json()
            if res.get("status") == "OK":
                elemento = res["rows"][0]["elements"][0]
                duracion_normal = elemento["duration"]["value"] / 60
                duracion_trafico = (
                    elemento.get("duration_in_traffic", elemento["duration"])["value"] / 60
                )
                if duracion_trafico > duracion_normal + 10:
                    msg = (
                        f"🚗 *Alerta de Tráfico*\n¡Hola! Tu cita es en 2 horas. Detecté tráfico "
                        f"en tu ruta (aprox {int(duracion_trafico)} min). "
                        f"¡Te sugiero salir con anticipación! ✨"
                    )
                else:
                    msg = (
                        f"🚗 *Recordatorio Inpulso*\n¡Hola! Tu cita es en 2 horas. "
                        f"El tráfico está fluido ({int(duracion_trafico)} min). ¡Te esperamos! 😊"
                    )
                if enviar_mensaje_whatsapp(telefono, msg):
                    storage.marcar_recordatorio_enviado(event_id, "2h")
                return
        except requests.RequestException as e:
            logger.warning("Error Maps en recordatorio: %s", e)

    msg = (
        "🚗 *Recordatorio Inpulso*\n¡Hola! Paso a recordarte que tu cita es en aprox 2 horas. "
        "Contempla el tiempo de estacionamiento (sujeto a un cajón disponible). ¡Te esperamos! ✨"
    )
    if enviar_mensaje_whatsapp(telefono, msg):
        storage.marcar_recordatorio_enviado(event_id, "2h")


def alertas_citas_background():
    ahora_aware = datetime.datetime.now(ZONA)
    ahora_naive = ahora_aware.replace(tzinfo=None)
    try:
        service = get_calendar_service()
        time_min = ahora_aware.isoformat()
        time_max = (ahora_aware + datetime.timedelta(hours=25)).isoformat()

        for cal_id in config.DIRECTORIO_CALENDARIOS.values():
            events_result = service.events().list(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            for event in events_result.get("items", []):
                start_str = event["start"].get("dateTime")
                if not start_str:
                    continue

                event_id = event.get("id", "")
                hora_cita = (
                    datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    .astimezone(ZONA)
                    .replace(tzinfo=None)
                )
                diferencia = hora_cita - ahora_naive

                desc = event.get("description", "")
                phone_match = re.search(r"Teléfono:\s*(\+?\d+)", desc)
                if not phone_match:
                    continue
                telefono = phone_match.group(1)

                if datetime.timedelta(minutes=1425) <= diferencia <= datetime.timedelta(minutes=1440):
                    _enviar_recordatorio_24h(telefono, hora_cita, event_id)
                elif datetime.timedelta(minutes=110) <= diferencia <= datetime.timedelta(minutes=125):
                    _enviar_recordatorio_2h(telefono, hora_cita, event_id)
    except Exception as e:
        logger.error("Error alertas background: %s", e)


def verificar_lista_espera_background():
    if not config.ID_HOJA_CALCULO:
        return
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Lista_Espera!A:F"
        ).execute()
        rows = result.get("values", [])

        for i, row in enumerate(rows):
            if len(row) >= 6 and row[5] == "PENDIENTE":
                nombre, telefono, especialista, fecha = row[1], row[2], row[3], row[4]
                disp = consultar_agenda(fecha, especialista)
                if "Espacios DISPONIBLES" in disp:
                    horarios_texto = disp.split("): ")[1] if "): " in disp else disp
                    msg = (
                        f"✨ ¡Hola {nombre}!\n\nTe escribo de Inpulso 43 porque se acaba de "
                        f"liberar un espacio con {especialista.title()} para el {fecha}. 🎉\n\n"
                        f"Los horarios que se abrieron son: {horarios_texto}\n\n"
                        f"¿Te gustaría aprovechar y agendar? Avísame pronto antes de que "
                        f"alguien más lo tome. 😊"
                    )
                    if enviar_mensaje_whatsapp(telefono, msg):
                        service.spreadsheets().values().update(
                            spreadsheetId=config.ID_HOJA_CALCULO,
                            range=f"Lista_Espera!F{i+1}",
                            valueInputOption="USER_ENTERED",
                            body={"values": [["NOTIFICADO"]]},
                        ).execute()
    except Exception as e:
        logger.error("Error lista de espera: %s", e)
