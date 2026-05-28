import datetime
import json
import logging
import re
import urllib.parse
from pathlib import Path

import pytz
import requests

import config
from google_client import get_calendar_service, get_sheets_service

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)
PRECIOS_PATH = Path(__file__).resolve().parent / "precios.json"


def _resolver_especialista(especialista: str) -> str | None:
    especialista_completo = especialista.lower()
    for nombre in config.DIRECTORIO_CALENDARIOS:
        if nombre in especialista_completo:
            return nombre
    return None


def _obtener_eventos_dia(calendar_id: str, fecha: str):
    service = get_calendar_service()
    time_min = f"{fecha}T00:00:00-06:00"
    time_max = f"{fecha}T23:59:59-06:00"
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return events_result.get("items", [])


def _parsear_ocupados(events, base_date: datetime.datetime):
    ocupados = []
    for event in events:
        start_str = event["start"].get("dateTime")
        end_str = event["end"].get("dateTime")
        if start_str and end_str:
            s_time = (
                datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                .astimezone(ZONA)
                .replace(tzinfo=None)
            )
            e_time = (
                datetime.datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                .astimezone(ZONA)
                .replace(tzinfo=None)
            )
            ocupados.append((s_time, e_time))
        elif event["start"].get("date"):
            return None, True
    return ocupados, False


def slot_disponible(fecha_hora: datetime.datetime, nombre_clave: str) -> bool:
    """Verifica si un horario específico de 1 hora está libre."""
    calendar_id = config.DIRECTORIO_CALENDARIOS[nombre_clave]
    fecha = fecha_hora.strftime("%Y-%m-%d")
    events = _obtener_eventos_dia(calendar_id, fecha)
    ocupados, dia_bloqueado = _parsear_ocupados(events, fecha_hora)
    if dia_bloqueado:
        return False

    slot_inicio = fecha_hora.replace(minute=0, second=0, microsecond=0)
    if slot_inicio.hour < 7 or slot_inicio.hour >= 19:
        return False

    slot_fin = slot_inicio + datetime.timedelta(hours=1)
    for o_start, o_end in ocupados:
        if max(slot_inicio, o_start) < min(slot_fin, o_end):
            return False
    return True


def consultar_precios_y_servicios(especialista: str = "todos"):
    try:
        with open(PRECIOS_PATH, "r", encoding="utf-8") as f:
            catalogo = json.load(f)
        esp_lower = especialista.lower()
        for key in catalogo:
            if key in esp_lower:
                return f"Precios de {key}: " + json.dumps(catalogo[key], ensure_ascii=False)
        return "Catálogo completo: " + json.dumps(catalogo, ensure_ascii=False)
    except OSError as e:
        logger.error("Error leyendo precios.json: %s", e)
        return "Error interno al leer la base de datos de precios."


def consultar_agenda(fecha: str, especialista: str):
    nombre_clave = _resolver_especialista(especialista)
    if not nombre_clave:
        return f"No tengo la agenda de {especialista}."

    try:
        base_date = datetime.datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        return "Error: La fecha debe estar en formato exacto YYYY-MM-DD."

    calendar_id = config.DIRECTORIO_CALENDARIOS[nombre_clave]
    events = _obtener_eventos_dia(calendar_id, fecha)
    ocupados, dia_bloqueado = _parsear_ocupados(events, base_date)
    if dia_bloqueado:
        return f"El {fecha}, {nombre_clave} tiene bloqueado todo el día."

    horarios_disponibles = []
    slot_actual = base_date.replace(hour=7, minute=0)
    slot_fin_dia = base_date.replace(hour=19, minute=0)

    while slot_actual < slot_fin_dia:
        slot_siguiente = slot_actual + datetime.timedelta(hours=1)
        conflicto = False
        for o_start, o_end in ocupados:
            if max(slot_actual, o_start) < min(slot_siguiente, o_end):
                conflicto = True
                break
        if not conflicto:
            horarios_disponibles.append(slot_actual.strftime("%H:%M"))
        slot_actual += datetime.timedelta(hours=1)

    if not horarios_disponibles:
        return f"El {fecha}, {nombre_clave} NO tiene espacios disponibles."

    return (
        f"Espacios DISPONIBLES para {nombre_clave} el {fecha} (Citas de 1 hora): "
        + ", ".join(horarios_disponibles)
    )


def _normalizar_telefono_digitos(telefono: str) -> str:
    target_digits = re.sub(r"\D", "", telefono)
    if target_digits.startswith("521") and len(target_digits) == 13:
        target_digits = target_digits.replace("521", "52", 1)
    return target_digits[-10:] if len(target_digits) >= 10 else target_digits


def agendar_cita(
    servicio: str,
    fecha_hora: str,
    nombre_paciente: str,
    especialista: str,
    telefono_paciente: str = "",
):
    nombre_clave = _resolver_especialista(especialista)
    if not nombre_clave:
        return "ERROR CRITICO: Especialista no encontrado."

    try:
        if len(fecha_hora) == 10:
            return "ERROR CRITICO: Solo enviaste la fecha. Debes proporcionar fecha y hora exacta."

        fecha_hora = fecha_hora.replace(" ", "T")
        if len(fecha_hora) == 16:
            fecha_hora += ":00"

        fecha_inicio = datetime.datetime.fromisoformat(fecha_hora)
        if not slot_disponible(fecha_inicio, nombre_clave):
            return (
                "ERROR CRITICO: Ese horario ya no está disponible. "
                "Consulta la agenda nuevamente y ofrece otro horario."
            )

        fecha_fin = fecha_inicio + datetime.timedelta(hours=1)
        calendar_id = config.DIRECTORIO_CALENDARIOS[nombre_clave]
        service = get_calendar_service()

        nombres_detallados = {
            "juan": "Juan",
            "sara": "Sara Rosales",
            "patricia": "Patricia",
            "ivan": "Iván",
            "nutricion": "Nutricionista",
        }
        especialista_texto = nombres_detallados.get(nombre_clave, especialista.title())

        event = {
            "summary": nombre_paciente.upper(),
            "description": (
                f"Cita de {servicio} con {especialista_texto}. "
                f"Teléfono: {telefono_paciente}"
            ),
            "start": {
                "dateTime": fecha_inicio.isoformat(),
                "timeZone": config.ZONA_MEXICO,
            },
            "end": {
                "dateTime": fecha_fin.isoformat(),
                "timeZone": config.ZONA_MEXICO,
            },
        }

        evento_creado = service.events().insert(calendarId=calendar_id, body=event).execute()
        if not evento_creado.get("id"):
            return "ERROR CRITICO: Google Calendar no devolvió confirmación."

        _quitar_de_lista_espera(telefono_paciente)

        format_start = fecha_inicio.strftime("%Y%m%dT%H%M%S")
        format_end = fecha_fin.strftime("%Y%m%dT%H%M%S")
        texto_link = urllib.parse.quote(f"Cita en Inpulso con {especialista_texto}")
        detalles_link = urllib.parse.quote(
            f"Tu cita de {servicio} en Inpulso está confirmada."
        )
        ubicacion_link = urllib.parse.quote("Av. Hidalgo 533, República, 45146 Zapopan, Jal.")
        enlace_gigante = (
            f"https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={texto_link}&dates={format_start}/{format_end}"
            f"&details={detalles_link}&location={ubicacion_link}&ctz=America/Mexico_City"
        )

        try:
            enlace_corto = requests.get(
                f"http://tinyurl.com/api-create.php?url={enlace_gigante}",
                timeout=10,
            ).text
        except requests.RequestException:
            enlace_corto = enlace_gigante

        return (
            f"ÉXITO: Cita guardada correctamente. INSTRUCCIÓN PARA LA IA: "
            f"Confírmale al paciente con mucha calidez y entusiasmo que su cita está lista, "
            f"y entrégale este enlace: {enlace_corto}"
        )
    except Exception as e:
        logger.error("Error al agendar cita: %s", e)
        return "ERROR CRÍTICO AL AGENDAR: No se pudo guardar la cita."


def _quitar_de_lista_espera(telefono_paciente: str):
    if not telefono_paciente or not config.ID_HOJA_CALCULO:
        return
    try:
        service = get_sheets_service()
        sheet_metadata = service.spreadsheets().get(
            spreadsheetId=config.ID_HOJA_CALCULO
        ).execute()
        sheet_id_espera = None
        for s in sheet_metadata.get("sheets", []):
            if s.get("properties", {}).get("title") == "Lista_Espera":
                sheet_id_espera = s.get("properties", {}).get("sheetId")
                break
        if sheet_id_espera is None:
            return

        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Lista_Espera!A:F"
        ).execute()
        rows = result.get("values", [])
        target_10_digits = _normalizar_telefono_digitos(telefono_paciente)

        for i in range(len(rows) - 1, 0, -1):
            row = rows[i]
            if len(row) >= 3:
                row_phone_digits = re.sub(r"\D", "", row[2])
                if target_10_digits in row_phone_digits:
                    body = {
                        "requests": [
                            {
                                "deleteDimension": {
                                    "range": {
                                        "sheetId": sheet_id_espera,
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
                    break
    except Exception as e:
        logger.warning("Error al borrar de lista de espera: %s", e)


def cancelar_cita_paciente(telefono_paciente: str):
    try:
        service = get_calendar_service()
        ahora_aware = datetime.datetime.now(ZONA)
        ahora_naive = ahora_aware.replace(tzinfo=None)
        hoy_utc = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        target_10_digits = _normalizar_telefono_digitos(telefono_paciente)

        for cal_id in config.DIRECTORIO_CALENDARIOS.values():
            events_result = service.events().list(
                calendarId=cal_id,
                timeMin=hoy_utc,
                maxResults=50,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            for event in events_result.get("items", []):
                desc_digits = re.sub(r"\D", "", event.get("description", ""))
                if target_10_digits in desc_digits and len(target_10_digits) > 5:
                    start_str = event["start"].get("dateTime")
                    penalizacion_msg = ""
                    if start_str:
                        hora_cita = (
                            datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                            .astimezone(ZONA)
                            .replace(tzinfo=None)
                        )
                        diferencia = hora_cita - ahora_naive
                        if datetime.timedelta(hours=0) < diferencia < datetime.timedelta(hours=24):
                            penalizacion_msg = (
                                " IMPORTANTE: La cita se está cancelando con menos de 24 horas "
                                "de anticipación. Infórmale al paciente con muchísimo tacto, "
                                "empatía y amabilidad que, por políticas de la clínica, esto "
                                "genera una penalización del 50% del valor de la sesión."
                            )
                        else:
                            penalizacion_msg = (
                                " La cita se canceló con buen tiempo de anticipación "
                                "(sin penalización)."
                            )
                    service.events().delete(calendarId=cal_id, eventId=event["id"]).execute()
                    return (
                        f"INSTRUCCIÓN PARA LA IA: La cita fue cancelada exitosamente "
                        f"en el calendario.{penalizacion_msg} Confírmale al paciente de forma "
                        f"muy amable y humana."
                    )
        return (
            "INSTRUCCIÓN PARA LA IA: No encontré ninguna cita futura registrada con ese "
            "número de teléfono. Pídele al paciente que verifique el número amablemente."
        )
    except Exception as e:
        logger.error("Error cancelar cita: %s", e)
        return (
            "INSTRUCCIÓN PARA LA IA: Hubo un fallo técnico al cancelar la cita. "
            "Discúlpate amablemente."
        )


def agregar_lista_espera(nombre: str, telefono: str, especialista: str, fecha: str):
    if not config.ID_HOJA_CALCULO:
        return "INSTRUCCIÓN PARA LA IA: Hubo un fallo técnico. Dile al paciente que no pudiste agregarlo."
    try:
        service = get_sheets_service()
        fecha_registro = datetime.datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")
        valores = [[fecha_registro, nombre, telefono, especialista, fecha, "PENDIENTE"]]
        service.spreadsheets().values().append(
            spreadsheetId=config.ID_HOJA_CALCULO,
            range="Lista_Espera!A:F",
            valueInputOption="USER_ENTERED",
            body={"values": valores},
        ).execute()
        return (
            "INSTRUCCIÓN PARA LA IA: Dile al paciente con mucha empatía y calidez que "
            "ya lo anotaste en la lista de espera prioritaria para ese día."
        )
    except Exception as e:
        logger.error("Error lista de espera: %s", e)
        return (
            "INSTRUCCIÓN PARA LA IA: Hubo un fallo técnico al conectarse a Sheets. "
            "Disculpate con el paciente."
        )


def buscar_cita_paciente(nombre_paciente: str, especialista: str):
    nombre_clave = _resolver_especialista(especialista)
    if not nombre_clave:
        return "Especialista no reconocido."

    calendar_id = config.DIRECTORIO_CALENDARIOS[nombre_clave]
    service = get_calendar_service()
    hoy_utc = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=hoy_utc,
        maxResults=10,
        q=nombre_paciente,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    events = events_result.get("items", [])
    if not events:
        return f"No encontré citas para {nombre_paciente}."

    citas = []
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        citas.append(f"El {start[:10]} a las {start[11:16]}")
    return "Citas: " + ", ".join(citas)


def obtener_ruta_inpulso(ubicacion_paciente: str):
    if config.API_KEY_MAPS:
        try:
            url = (
                "https://maps.googleapis.com/maps/api/distancematrix/json"
                f"?origins={ubicacion_paciente}"
                "&destinations=Av.+Hidalgo+533,Zapopan"
                "&departure_time=now&language=es"
                f"&key={config.API_KEY_MAPS}"
            )
            res = requests.get(url, timeout=15).json()
            if res.get("status") == "OK":
                elemento = res["rows"][0]["elements"][0]
                duracion = elemento.get("duration_in_traffic", elemento["duration"])["text"]
                return (
                    f"INSTRUCCIÓN PARA LA IA: Dile al paciente textualmente de forma muy "
                    f"cálida y con emojis que hará aproximadamente {duracion} de camino en "
                    f"auto hacia la clínica."
                )
        except requests.RequestException as e:
            logger.warning("Error Google Maps: %s", e)
    return (
        "INSTRUCCIÓN PARA LA IA: Dile al paciente con mucha calidez: "
        "'¡Ya guardé tu ubicación! 😊 Considera el tráfico habitual para llegar a tiempo.'"
    )


def calcular_gasto_combustible(vehiculo: str, kilometros: float, rendimiento_km_l: float):
    precio_gasolina = 24.50
    costo = (kilometros / rendimiento_km_l) * precio_gasolina
    return f"${costo:.2f} MXN."


def colorear_celda_pago(service, sheet_id, row_index, estatus):
    if estatus == "PAGADO":
        r, g, b = 0.78, 0.93, 0.80
    else:
        r, g, b = 1.0, 0.8, 0.8
    body = {
        "requests": [
            {
                "updateCells": {
                    "rows": [
                        {
                            "values": [
                                {
                                    "userEnteredValue": {"stringValue": estatus},
                                    "userEnteredFormat": {
                                        "backgroundColor": {"red": r, "green": g, "blue": b},
                                        "horizontalAlignment": "CENTER",
                                        "textFormat": {"bold": True},
                                    },
                                }
                            ]
                        }
                    ],
                    "fields": (
                        "userEnteredValue,userEnteredFormat.backgroundColor,"
                        "userEnteredFormat.horizontalAlignment,userEnteredFormat.textFormat.bold"
                    ),
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_index,
                        "endRowIndex": row_index + 1,
                        "startColumnIndex": 5,
                        "endColumnIndex": 6,
                    },
                }
            }
        ]
    }
    service.spreadsheets().batchUpdate(spreadsheetId=config.ID_HOJA_CALCULO, body=body).execute()


def registrar_paciente_taller(
    nombre: str, telefono: str, nombre_taller: str, correo: str = "No proporcionado"
):
    if not config.ID_HOJA_CALCULO:
        return (
            "INSTRUCCIÓN PARA LA IA: Hubo un fallo técnico. Dile al paciente amablemente "
            "que no pudiste guardar sus datos en este momento."
        )
    try:
        service = get_sheets_service()
        sheet_metadata = service.spreadsheets().get(
            spreadsheetId=config.ID_HOJA_CALCULO
        ).execute()
        sheet_id = 0
        for s in sheet_metadata.get("sheets", []):
            if s.get("properties", {}).get("title") == "Inscripciones":
                sheet_id = s.get("properties", {}).get("sheetId", 0)
                break

        fecha_registro = datetime.datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")
        valores = [[fecha_registro, nombre, telefono, correo, nombre_taller, "PENDIENTE"]]
        response = service.spreadsheets().values().append(
            spreadsheetId=config.ID_HOJA_CALCULO,
            range="Inscripciones!A:F",
            valueInputOption="USER_ENTERED",
            body={"values": valores},
        ).execute()

        updated_range = response.get("updates", {}).get("updatedRange", "")
        match = re.search(r"A(\d+):", updated_range)
        if match:
            colorear_celda_pago(service, sheet_id, int(match.group(1)) - 1, "PENDIENTE")

        return (
            "INSTRUCCIÓN PARA LA IA: Confírmale al paciente de forma muy alegre, humana "
            "y con emojis que sus datos han sido registrados con éxito. NOTA: El pago queda "
            "PENDIENTE hasta que recepción lo confirme manualmente."
        )
    except Exception as e:
        logger.error("Error registrar taller: %s", e)
        return "INSTRUCCIÓN PARA LA IA: Hubo un fallo al registrar en Sheets."


def actualizar_pago_paciente(telefono: str, estatus: str = "PAGADO"):
    try:
        service = get_sheets_service()
        sheet_metadata = service.spreadsheets().get(
            spreadsheetId=config.ID_HOJA_CALCULO
        ).execute()
        sheet_id = 0
        for s in sheet_metadata.get("sheets", []):
            if s.get("properties", {}).get("title") == "Inscripciones":
                sheet_id = s.get("properties", {}).get("sheetId", 0)
                break

        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Inscripciones!A:E"
        ).execute()
        rows = result.get("values", [])
        target_10_digits = _normalizar_telefono_digitos(telefono)
        row_index = None

        for i in range(len(rows) - 1, -1, -1):
            if len(rows[i]) > 2:
                row_phone_digits = re.sub(r"\D", "", rows[i][2])
                if target_10_digits in row_phone_digits and len(target_10_digits) > 5:
                    row_index = i
                    break

        if row_index is not None:
            colorear_celda_pago(service, sheet_id, row_index, estatus)
            return (
                f"INSTRUCCIÓN PARA LA IA: Estatus de pago actualizado a {estatus}. "
                f"Agradécele al paciente de forma muy cálida."
            )
        return (
            "INSTRUCCIÓN PARA LA IA: No encontré registro previo para ese teléfono. "
            "Pide que te confirmen el número con amabilidad."
        )
    except Exception as e:
        logger.error("Error actualizar pago: %s", e)
        return "INSTRUCCIÓN PARA LA IA: Fallo técnico al actualizar el pago."
