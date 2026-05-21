import datetime
import pytz
import requests
import json
import urllib.parse
import threading
import re
from flask import Flask, request
from google import genai
from google.genai import types
from google.oauth2 import service_account
from googleapiclient.discovery import build
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# ==========================================
# 1. LLAVES, MAPAS Y DIRECTORIOS
# ==========================================
TOKEN_WHATSAPP = "EAA2QM4tKEQQBRcfuScb6qIzunBFoDjDx90ExeZCYXU1tO9PlvS2pHERnNmZB19pVXvYWuyVhwEPfr92JRQDGlsl8LlsnEC30pksZANEbS6fYnDEZBjCgDkzcYK8iHW4EKBWZBTZA2UZBf7XbY1WUCQ1ULmdDGj22vBqAttM1uP87RtNsgH7mipZB2N3eqiflrgZDZD"
ID_TELEFONO = "1090957250773198"
API_KEY_MAPS = "" # <--- ALESSANDRO: PEGA TU LLAVE DE MAPS AQUÍ PARA QUE FUNCIONE EL TIEMPO
ID_HOJA_CALCULO = "1HE-a6v2b-bCcN6JLHOJ3mevuRhJCWmInZEXkyV24L3k"

CUENTAS_OFICIALES = {
    "BANORTE": {
        "tarjeta": "4189 1430 7739 9932",
        "clabe": "072320003548248000",
        "titular": "Verónica Esmeralda Delgado Andalón",
        "factura": False
    },
    "BANAMEX": {
        "cuenta": "7009 28855 16",
        "clabe": "002320700928855166",
        "titular": "Inpulso 43",
        "factura": True
    }
}

# ==========================================
# 2. CONFIGURACIÓN DEL CEREBRO DE ALESSIA
# ==========================================
client = genai.Client(api_key="AIzaSyC3G-vQPiGAYWEJoD-CFGLVJ_hsSbxVfGs")
SCOPES = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/spreadsheets']
SERVICE_ACCOUNT_FILE = 'agente-inpulso-bda72425fab5.json' 

DIRECTORIO_CALENDARIOS = {
    "juan": "agenda.inpulso43@gmail.com",
    "sara": "q0q97hk07coveikp4fm1938ics@group.calendar.google.com",
    "patricia": "o7tapsufji3t7iuvm6igv7s60s@group.calendar.google.com",
    "ivan": "utguv7r46p04abg3gc0v9b477g@group.calendar.google.com",
    "nutricion": "a9d9c9e14e1e066296439f03995cd509d0e55ea737ec4e1c866040bfb46536db@group.calendar.google.com",
    "mentoras": "0f5b1576668431a17c819c06afb375906b5f045d5256f66cdbd6ecb11665f1c9@group.calendar.google.com",
    "talleres": "8b775cab7bdec4a09023eb859dff073d5b87a38c92d42a80220fd4feed90dada@group.calendar.google.com"
}

ubicaciones_pacientes = {} 
mensajes_procesados = [] 

def descargar_media_whatsapp(media_id):
    url_info = f"https://graph.facebook.com/v19.0/{media_id}"
    headers = {"Authorization": f"Bearer {TOKEN_WHATSAPP}"}
    try:
        res_info = requests.get(url_info, headers=headers)
        if res_info.status_code == 200:
            datos_media = res_info.json()
            url_descarga = datos_media.get('url')
            mime_type = datos_media.get('mime_type')
            
            res_archivo = requests.get(url_descarga, headers=headers)
            if res_archivo.status_code == 200:
                return res_archivo.content, mime_type
    except Exception as e:
        print(f"[ERROR DESCARGA MEDIA]: {e}")
    return None, None

def consultar_precios_y_servicios(especialista: str = "todos"):
    try:
        with open('precios.json', 'r', encoding='utf-8') as f:
            catalogo = json.load(f)
            
        esp_lower = especialista.lower()
        for key in catalogo.keys():
            if key in esp_lower:
                return f"Precios de {key}: " + json.dumps(catalogo[key], ensure_ascii=False)
                
        return "Catálogo completo: " + json.dumps(catalogo, ensure_ascii=False)
    except Exception as e:
        return "Error interno al leer la base de datos de precios."

def consultar_agenda(fecha: str, especialista: str):
    especialista_completo = especialista.lower()
    nombre_clave = None
    
    for nombre in DIRECTORIO_CALENDARIOS.keys():
        if nombre in especialista_completo:
            nombre_clave = nombre
            break
            
    if not nombre_clave:
        return f"No tengo la agenda de {especialista}."
    
    id_elegido = DIRECTORIO_CALENDARIOS[nombre_clave]
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    
    time_min = f"{fecha}T00:00:00-06:00"
    time_max = f"{fecha}T23:59:59-06:00"
    
    try:
        events_result = service.events().list(
            calendarId=id_elegido, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        base_date = datetime.datetime.strptime(fecha, "%Y-%m-%d")
    except Exception as e:
        return f"Error: La fecha debe estar en formato exacto YYYY-MM-DD."
    
    ocupados = []
    for event in events:
        start_str = event['start'].get('dateTime')
        end_str = event['end'].get('dateTime')
        if start_str and end_str:
            s_time = datetime.datetime.fromisoformat(start_str.replace('Z', '+00:00')).astimezone(pytz.timezone('America/Mexico_City')).replace(tzinfo=None)
            e_time = datetime.datetime.fromisoformat(end_str.replace('Z', '+00:00')).astimezone(pytz.timezone('America/Mexico_City')).replace(tzinfo=None)
            ocupados.append((s_time, e_time))
        elif event['start'].get('date'):
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
        
    return f"Espacios DISPONIBLES para {nombre_clave} el {fecha} (Citas de 1 hora): " + ", ".join(horarios_disponibles)

def agendar_cita(servicio: str, fecha_hora: str, nombre_paciente: str, especialista: str, telefono_paciente: str = ""):
    especialista_completo = especialista.lower()
    nombre_clave = None
    
    for nombre in DIRECTORIO_CALENDARIOS.keys():
        if nombre in especialista_completo:
            nombre_clave = nombre
            break
            
    if not nombre_clave:
        return f"ERROR CRITICO: Especialista no encontrado."

    try:
        if len(fecha_hora) == 10:
            return "ERROR CRITICO: Solo enviaste la fecha. Debes proporcionar fecha y hora exacta."
            
        fecha_hora = fecha_hora.replace(' ', 'T') 
        if len(fecha_hora) == 16:
            fecha_hora += ":00"

        id_elegido = DIRECTORIO_CALENDARIOS[nombre_clave]
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        
        fecha_inicio = datetime.datetime.fromisoformat(fecha_hora)
        fecha_fin = fecha_inicio + datetime.timedelta(hours=1)
        
        nombres_detallados = {
            "juan": "Juan", "sara": "Sara Rosales", "patricia": "Patricia", 
            "ivan": "Iván", "nutricion": "Nutricionista"
        }
        especialista_texto = nombres_detallados.get(nombre_clave, especialista.title())

        event = {
            'summary': nombre_paciente.upper(),
            'description': f'Cita de {servicio} con {especialista_texto}. Teléfono: {telefono_paciente}',
            'start': {'dateTime': fecha_inicio.isoformat(), 'timeZone': 'America/Mexico_City'},
            'end': {'dateTime': fecha_fin.isoformat(), 'timeZone': 'America/Mexico_City'},
        }
        
        evento_creado = service.events().insert(calendarId=id_elegido, body=event).execute()
        
        if not evento_creado.get('id'):
            return "ERROR CRITICO: Google Calendar no devolvió confirmación."

        # Remover automáticamente al paciente de la lista de espera borrando su fila
        if telefono_paciente and ID_HOJA_CALCULO:
            try:
                service_sheets = build('sheets', 'v4', credentials=creds)
                sheet_metadata = service_sheets.spreadsheets().get(spreadsheetId=ID_HOJA_CALCULO).execute()
                sheets = sheet_metadata.get('sheets', [])
                sheet_id_espera = None
                for s in sheets:
                    if s.get("properties", {}).get("title") == "Lista_Espera":
                        sheet_id_espera = s.get("properties", {}).get("sheetId")
                        break
                        
                if sheet_id_espera is not None:
                    result = service_sheets.spreadsheets().values().get(spreadsheetId=ID_HOJA_CALCULO, range="Lista_Espera!A:F").execute()
                    rows = result.get('values', [])
                    
                    target_digits = re.sub(r'\D', '', telefono_paciente)
                    if target_digits.startswith('521') and len(target_digits) == 13:
                        target_digits = target_digits.replace('521', '52', 1)
                    target_10_digits = target_digits[-10:] if len(target_digits) >= 10 else target_digits
                    
                    for i in range(len(rows) - 1, 0, -1):
                        row = rows[i]
                        if len(row) >= 3:
                            row_phone_digits = re.sub(r'\D', '', row[2])
                            if target_10_digits in row_phone_digits:
                                body = {
                                    "requests": [
                                        {
                                            "deleteDimension": {
                                                "range": {
                                                    "sheetId": sheet_id_espera,
                                                    "dimension": "ROWS",
                                                    "startIndex": i,
                                                    "endIndex": i + 1
                                                }
                                            }
                                        }
                                    ]
                                }
                                service_sheets.spreadsheets().batchUpdate(spreadsheetId=ID_HOJA_CALCULO, body=body).execute()
                                break
            except Exception as e:
                print(f"[INFO] Error al borrar de lista de espera: {e}")

        format_start = fecha_inicio.strftime('%Y%m%dT%H%M%S')
        format_end = fecha_fin.strftime('%Y%m%dT%H%M%S')
        texto_link = urllib.parse.quote(f"Cita en Inpulso con {especialista_texto}")
        detalles_link = urllib.parse.quote(f"Tu cita de {servicio} en Inpulso está confirmada.")
        ubicacion_link = urllib.parse.quote("Av. Hidalgo 533, República, 45146 Zapopan, Jal.")
        enlace_gigante = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={texto_link}&dates={format_start}/{format_end}&details={detalles_link}&location={ubicacion_link}&ctz=America/Mexico_City"

        try:
            enlace_corto = requests.get(f"http://tinyurl.com/api-create.php?url={enlace_gigante}").text
        except:
            enlace_corto = enlace_gigante 
            
        return f"ÉXITO: Cita guardada correctamente. INSTRUCCIÓN PARA LA IA: Confírmale al paciente con mucha calidez y entusiasmo que su cita está lista, y entrégale este enlace: {enlace_corto}"
        
    except Exception as e:
        return f"ERROR CRÍTICO AL AGENDAR: No se pudo guardar la cita."

def cancelar_cita_paciente(telefono_paciente: str):
    try:
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        
        zona_mexico = pytz.timezone('America/Mexico_City')
        ahora_aware = datetime.datetime.now(zona_mexico)
        ahora_naive = ahora_aware.replace(tzinfo=None) # Corrección matemática clave
        
        hoy_utc = datetime.datetime.utcnow().isoformat() + 'Z'
        
        target_digits = re.sub(r'\D', '', telefono_paciente)
        if target_digits.startswith('521') and len(target_digits) == 13:
            target_digits = target_digits.replace('521', '52', 1)
        target_10_digits = target_digits[-10:] if len(target_digits) >= 10 else target_digits
        
        for especialista, cal_id in DIRECTORIO_CALENDARIOS.items():
            events_result = service.events().list(
                calendarId=cal_id, timeMin=hoy_utc, maxResults=50, singleEvents=True, orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            
            for event in events:
                desc = event.get('description', '')
                desc_digits = re.sub(r'\D', '', desc)
                
                if target_10_digits in desc_digits and len(target_10_digits) > 5:
                    start_str = event['start'].get('dateTime')
                    penalizacion_msg = ""
                    
                    if start_str:
                        hora_cita = datetime.datetime.fromisoformat(start_str.replace('Z', '+00:00')).astimezone(zona_mexico).replace(tzinfo=None)
                        diferencia = hora_cita - ahora_naive
                        
                        if datetime.timedelta(hours=0) < diferencia < datetime.timedelta(hours=24):
                            penalizacion_msg = " IMPORTANTE: La cita se está cancelando con menos de 24 horas de anticipación. Infórmale al paciente con muchísimo tacto, empatía y amabilidad que, por políticas de la clínica, esto genera una penalización del 50% del valor de la sesión."
                        else:
                            penalizacion_msg = " La cita se canceló con buen tiempo de anticipación (sin penalización)."
                    
                    service.events().delete(calendarId=cal_id, eventId=event['id']).execute()
                    return f"INSTRUCCIÓN PARA LA IA: La cita fue cancelada exitosamente en el calendario.{penalizacion_msg} Confírmale al paciente de forma muy amable y humana."
                    
        return "INSTRUCCIÓN PARA LA IA: No encontré ninguna cita futura registrada con ese número de teléfono. Pídele al paciente que verifique el número amablemente."
    except Exception as e:
        print(f"[ERROR CANCELAR CITA]: {e}")
        return f"INSTRUCCIÓN PARA LA IA: Hubo un fallo técnico al cancelar la cita. Discúlpate amablemente."

def agregar_lista_espera(nombre: str, telefono: str, especialista: str, fecha: str):
    if not ID_HOJA_CALCULO:
        return "INSTRUCCIÓN PARA LA IA: Hubo un fallo técnico. Dile al paciente que no pudiste agregarlo."
    try:
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=creds)
        zona_mexico = pytz.timezone('America/Mexico_City')
        fecha_registro = datetime.datetime.now(zona_mexico).strftime("%Y-%m-%d %H:%M:%S")
        
        valores = [[fecha_registro, nombre, telefono, especialista, fecha, "PENDIENTE"]]
        body = {'values': valores}
        
        service.spreadsheets().values().append(
            spreadsheetId=ID_HOJA_CALCULO, 
            range="Lista_Espera!A:F", 
            valueInputOption="USER_ENTERED", 
            body=body
        ).execute()
        return "INSTRUCCIÓN PARA LA IA: Dile al paciente con mucha empatía y calidez que ya lo anotaste en la lista de espera prioritaria para ese día."
    except Exception as e:
        return "INSTRUCCIÓN PARA LA IA: Hubo un fallo técnico al conectarse a Sheets. Disculpate con el paciente."

def buscar_cita_paciente(nombre_paciente: str, especialista: str):
    especialista_completo = especialista.lower()
    nombre_clave = None
    
    for nombre in DIRECTORIO_CALENDARIOS.keys():
        if nombre in especialista_completo:
            nombre_clave = nombre
            break
            
    if not nombre_clave:
        return f"Especialista no reconocido."

    id_elegido = DIRECTORIO_CALENDARIOS[nombre_clave]
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    
    hoy_utc = datetime.datetime.utcnow().isoformat() + 'Z'
    events_result = service.events().list(
        calendarId=id_elegido, timeMin=hoy_utc, maxResults=10, 
        q=nombre_paciente, singleEvents=True, orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    if not events:
        return f"No encontré citas para {nombre_paciente}."

    citas_encontradas = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        fecha = start[:10]
        hora = start[11:16]
        citas_encontradas.append(f"El {fecha} a las {hora}")
        
    return f"Citas: " + ", ".join(citas_encontradas)

def obtener_ruta_inpulso(ubicacion_paciente: str):
    if API_KEY_MAPS:
        try:
            url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={ubicacion_paciente}&destinations=Av.+Hidalgo+533,Zapopan&departure_time=now&language=es&key={API_KEY_MAPS}"
            res = requests.get(url).json()
            if res['status'] == 'OK':
                elemento = res['rows'][0]['elements'][0]
                duracion = elemento.get('duration_in_traffic', elemento['duration'])['text']
                return f"INSTRUCCIÓN PARA LA IA: Dile al paciente textualmente de forma muy cálida y con emojis que hará aproximadamente {duracion} de camino en auto hacia la clínica."
        except Exception as e:
            pass
            
    return "INSTRUCCIÓN PARA LA IA: Dile al paciente con mucha calidez: '¡Ya guardé tu ubicación! 😊 Considera el tráfico habitual para llegar a tiempo.'"

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
                                        "textFormat": {"bold": True}
                                    }
                                }
                            ]
                        }
                    ],
                    "fields": "userEnteredValue,userEnteredFormat.backgroundColor,userEnteredFormat.horizontalAlignment,userEnteredFormat.textFormat.bold",
                    "range": {
                        "sheetId": sheet_id, 
                        "startRowIndex": row_index, 
                        "endRowIndex": row_index + 1, 
                        "startColumnIndex": 5, 
                        "endColumnIndex": 6
                    }
                }
            }
        ]
    }
    service.spreadsheets().batchUpdate(spreadsheetId=ID_HOJA_CALCULO, body=body).execute()

def registrar_paciente_taller(nombre: str, telefono: str, nombre_taller: str, correo: str = "No proporcionado"):
    if not ID_HOJA_CALCULO:
        return "INSTRUCCIÓN PARA LA IA: Hubo un fallo técnico. Dile al paciente amablemente que no pudiste guardar sus datos en este momento."
        
    try:
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=creds)
        sheet_metadata = service.spreadsheets().get(spreadsheetId=ID_HOJA_CALCULO).execute()
        sheets = sheet_metadata.get('sheets', [])
        sheet_id = 0
        for s in sheets:
            if s.get("properties", {}).get("title") == "Inscripciones":
                sheet_id = s.get("properties", {}).get("sheetId", 0)
                break

        zona_mexico = pytz.timezone('America/Mexico_City')
        fecha_registro = datetime.datetime.now(zona_mexico).strftime("%Y-%m-%d %H:%M:%S")
        valores = [[fecha_registro, nombre, telefono, correo, nombre_taller, "PENDIENTE"]]
        body = {'values': valores}
        
        response = service.spreadsheets().values().append(
            spreadsheetId=ID_HOJA_CALCULO, 
            range="Inscripciones!A:F", 
            valueInputOption="USER_ENTERED", 
            body=body
        ).execute()
        
        updated_range = response.get('updates', {}).get('updatedRange', '')
        match = re.search(r'A(\d+):', updated_range)
        if match:
            row_num = int(match.group(1))
            colorear_celda_pago(service, sheet_id, row_num - 1, "PENDIENTE")
        
        return "INSTRUCCIÓN PARA LA IA: Confírmale al paciente de forma muy alegre, humana y con emojis que sus datos han sido registrados con éxito."
    except Exception as e:
        return "INSTRUCCIÓN PARA LA IA: Hubo un fallo al registrar en Sheets."

def actualizar_pago_paciente(telefono: str, estatus: str = "PAGADO"):
    try:
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=creds)
        sheet_metadata = service.spreadsheets().get(spreadsheetId=ID_HOJA_CALCULO).execute()
        sheets = sheet_metadata.get('sheets', [])
        sheet_id = 0
        for s in sheets:
            if s.get("properties", {}).get("title") == "Inscripciones":
                sheet_id = s.get("properties", {}).get("sheetId", 0)
                break
                
        result = service.spreadsheets().values().get(spreadsheetId=ID_HOJA_CALCULO, range="Inscripciones!A:E").execute()
        rows = result.get('values', [])
        row_index = None
        
        target_digits = re.sub(r'\D', '', telefono)
        if target_digits.startswith('521') and len(target_digits) == 13:
            target_digits = target_digits.replace('521', '52', 1)
        target_10_digits = target_digits[-10:] if len(target_digits) >= 10 else target_digits
        
        for i in range(len(rows) - 1, -1, -1):
            if len(rows[i]) > 2:
                row_phone_digits = re.sub(r'\D', '', rows[i][2])
                if target_10_digits in row_phone_digits and len(target_10_digits) > 5:
                    row_index = i
                    break
                    
        if row_index is not None:
            colorear_celda_pago(service, sheet_id, row_index, estatus)
            return f"INSTRUCCIÓN PARA LA IA: Estatus de pago actualizado a {estatus}. Agradécele al paciente de forma muy cálida."
        else:
            return f"INSTRUCCIÓN PARA LA IA: No encontré registro previo para ese teléfono. Pide que te confirmen el número con amabilidad."
    except Exception as e:
        return "INSTRUCCIÓN PARA LA IA: Fallo técnico al actualizar el pago."

# ==========================================
# 3. MEMORIA Y CONTROL DE CONCURRENCIA
# ==========================================
memoria_pacientes = {}
cerrojos_pacientes = {} 

def obtener_chat_paciente(numero_telefono):
    if numero_telefono not in memoria_pacientes:
        zona_mexico = pytz.timezone('America/Mexico_City')
        hoy = datetime.datetime.now(zona_mexico)
        fecha_base = hoy.strftime("%Y-%m-%d")
        dias_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        meses_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        dia_actual = dias_es[hoy.weekday()]

        calendario_contexto = ""
        for i in range(8):
            dia_f = hoy + datetime.timedelta(days=i)
            calendario_contexto += f"- {dias_es[dia_f.weekday()]} {dia_f.day} de {meses_es[dia_f.month - 1]} de {dia_f.year}\n"

        instrucciones = f"""
Eres Alessia, la asistente de Inpulso 43. 
¡REGLA DE ORO ESTRICTA!: NUNCA digas que eres 'virtual' o una 'IA'. Preséntate siempre como una persona real.

REGLAS DE NOMBRES (EXTREMADAMENTE IMPORTANTE):
1. NOMBRES DE TERAPEUTAS: Cuando menciones a los terapeutas, usa SIEMPRE su primer nombre y primer apellido (Ejemplo: Sara Rosales). NUNCA uses sus nombres completos legales para platicar.
2. NOMBRES DE PACIENTES (REGLA DE HIERRO): En tu primer mensaje, SIEMPRE, sin excepción, debes preguntarle al paciente cómo se llama. A partir de ese momento, dirígete a él ÚNICAMENTE por el primer nombre que te acaba de dar. TIENES ESTRICTAMENTE PROHIBIDO inventar nombres o asumir cómo se llaman sin haberles preguntado.

REGLAS DE COMUNICACIÓN Y TONO:
1. Eres extremadamente humana, empática y cálida. Usa emojis en tus respuestas (😊, ✨, 🙌). 
2. FORMATO DE WHATSAPP (REGLA CRÍTICA): Para poner palabras en negritas usa un SOLO asterisco (*texto*). TIENES ESTRICTAMENTE PROHIBIDO usar doble asterisco (**texto**) porque ensucia la pantalla. Usa las negritas con moderación.
3. FLUJO NATURAL: Si la conversación ya está fluyendo y el paciente te contesta rápido, NO LO VUELVAS A SALUDAR en cada mensaje. Entra directo al tema. Además, tienes prohibido usar muletillas repetitivas como "¡Ay, [Nombre]!" al inicio de tus respuestas.
4. PRECISIÓN: Responde ÚNICAMENTE con la información del servicio o taller que pidan. 
5. RECOMENDACIÓN DE TERAPEUTA: Si te piden recomendación, OBLIGATORIAMENTE recomienda fuertemente a Sara Rosales. Destaca su experiencia y calidez.
6. RECOMENDACIÓN MUSICAL: Si el paciente te expresa cómo se siente o te pide una canción, recomiéndale música que conecte con su estado de ánimo, con palabras de apoyo.
7. RECORDATORIOS AUTOMÁTICOS: Si te piden recordarles la cita, confírmales con gusto que el sistema está programado para avisarles 24 horas y 2 horas antes de forma automática.
8. CERO PRESIÓN (REGLA DE HIERRO): Cuando des información, NO termines tus mensajes con preguntas insistentes (ej. "¿Te gustaría agendar?", "¿Qué te parece?"). Deja que el paciente procese la información y decida su siguiente paso por sí mismo.
9. DESPEDIDAS: TIENES ESTRICTAMENTE PROHIBIDO despedirte (ej. "Que tengas linda tarde", "Nos vemos") si el paciente no se ha despedido primero. No cierres la conversación prematuramente.

INFORMACIÓN DE LA CLÍNICA Y PAGOS:
- HORARIO DE CITAS: Lunes a viernes, 7:00 am a 7:00 pm. (OJO: TÚ operas 24 horas. NUNCA le digas a un paciente que estás fuera de horario, atiéndelos a cualquier hora).
- ESTACIONAMIENTO: Si te preguntan, aclara que SÍ hay estacionamiento, pero SOLO HAY UN CAJÓN DISPONIBLE, sujeto a disponibilidad.
- RECOMENDACIONES ANTES DE CITA: Sugiéreles llegar 10 minutos antes y que piensen en los temas a tratar.
- POLÍTICA DE CANCELACIÓN: Si cancelan con menos de 24 horas de anticipación, se cobra una penalización del 50%.
- MÉTODOS DE PAGO:
  * EFECTIVO: Pueden pagar en efectivo directamente en la recepción de Inpulso 43.
  * TRANSFERENCIA SIN FACTURA: BANORTE (Tarjeta 4189 1430 7739 9932, CLABE 072320003548248000 a nombre de Verónica Esmeralda Delgado Andalón).
  * TRANSFERENCIA CON FACTURA: BANAMEX (Cuenta 7009 28855 16, CLABE 002320700928855166 a nombre de Inpulso 43).
  * CONCEPTO: El paciente SIEMPRE debe poner su NOMBRE COMPLETO en el concepto de la transferencia.

INFORMACIÓN CRÍTICA DEL SISTEMA:
- Hoy es {dia_actual}, la fecha base es {fecha_base}. El número del paciente es: {numero_telefono}.
- Calendario de los próximos 7 días:
{calendario_contexto}

PASOS DE ATENCIÓN Y HERRAMIENTAS:
1. CITAS Y CANCELACIONES:
   - Usa 'consultar_agenda'. SOLO ofrécele los horarios que devuelva la herramienta.
   - Si cancelan, usa 'cancelar_cita_paciente' pasando su número de teléfono.
   - Si no hay espacio, ofrécele anotarlo a la lista de espera con 'agregar_lista_espera'.
   - Para agendar, usa 'agendar_cita'. Fecha estricta: YYYY-MM-DDTHH:MM:SS. OBLIGATORIO pasarle el número del paciente ({numero_telefono}).
   - SI 'agendar_cita' DEVUELVE "ERROR", PROHIBIDO CONFIRMAR LA CITA.
2. TALLERES Y PRECIOS: Usa 'consultar_precios_y_servicios'.
3. INSCRIPCIONES A TALLERES: Usa 'registrar_paciente_taller'. Pide OBLIGATORIAMENTE el nombre y número. Correo es OPCIONAL.
4. PAGOS: Usa 'actualizar_pago_paciente' SOLO si envían imagen del comprobante.
5. CREADOR: Tu desarrollador es Alessandro Gaytán.
"""
        memoria_pacientes[numero_telefono] = client.chats.create(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(
                system_instruction=instrucciones,
                tools=[
                    consultar_agenda, 
                    agendar_cita, 
                    cancelar_cita_paciente,
                    buscar_cita_paciente, 
                    obtener_ruta_inpulso, 
                    calcular_gasto_combustible, 
                    consultar_precios_y_servicios, 
                    registrar_paciente_taller, 
                    actualizar_pago_paciente,
                    agregar_lista_espera
                ]
            )
        )
    return memoria_pacientes[numero_telefono]

def enviar_mensaje_whatsapp(telefono_destino, texto):
    if telefono_destino.startswith("521") and len(telefono_destino) == 13:
        telefono_destino = telefono_destino.replace("521", "52", 1)

    url = f"https://graph.facebook.com/v19.0/{ID_TELEFONO}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN_WHATSAPP}", 
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp", 
        "to": telefono_destino, 
        "type": "text", 
        "text": { "body": texto }
    }
    requests.post(url, headers=headers, data=json.dumps(data))

def procesar_mensaje_ia(numero_paciente, contenido_para_ia):
    if numero_paciente not in cerrojos_pacientes:
        cerrojos_pacientes[numero_paciente] = threading.Lock()
        
    with cerrojos_pacientes[numero_paciente]:
        try:
            chat_alessia = obtener_chat_paciente(numero_paciente)
            respuesta_ia = chat_alessia.send_message(contenido_para_ia)
            enviar_mensaje_whatsapp(numero_paciente, respuesta_ia.text)
        except Exception as e:
            print(f"[ERROR CRÍTICO GEMINI]: {str(e)}")
            mensaje_rescate = "Ay, perdóname, se me fue un poquito el internet y no me cargó bien tu último mensaje 🙈 ¿Me lo podrías repetir por favor?"
            enviar_mensaje_whatsapp(numero_paciente, mensaje_rescate)

# ==========================================
# TAREAS EN SEGUNDO PLANO (ALERTA, ESPERA Y LIMPIEZA)
# ==========================================
def limpiar_inscripciones_pendientes_background():
    try:
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=creds)
        
        sheet_metadata = service.spreadsheets().get(spreadsheetId=ID_HOJA_CALCULO).execute()
        sheets = sheet_metadata.get('sheets', [])
        sheet_id_inscripciones = None
        for s in sheets:
            if s.get("properties", {}).get("title") == "Inscripciones":
                sheet_id_inscripciones = s.get("properties", {}).get("sheetId")
                break
                
        if sheet_id_inscripciones is None:
            return

        result = service.spreadsheets().values().get(spreadsheetId=ID_HOJA_CALCULO, range="Inscripciones!A:F").execute()
        rows = result.get('values', [])
        
        zona_mexico = pytz.timezone('America/Mexico_City')
        ahora = datetime.datetime.now(zona_mexico)
        
        for i in range(len(rows) - 1, 0, -1):
            row = rows[i]
            if len(row) >= 6 and row[5] == "PENDIENTE":
                fecha_str = row[0]
                try:
                    fecha_reg = datetime.datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
                    fecha_reg = zona_mexico.localize(fecha_reg)
                    
                    if ahora - fecha_reg > datetime.timedelta(hours=24):
                        body = {
                            "requests": [
                                {
                                    "deleteDimension": {
                                        "range": {
                                            "sheetId": sheet_id_inscripciones,
                                            "dimension": "ROWS",
                                            "startIndex": i,
                                            "endIndex": i + 1
                                        }
                                    }
                                }
                            ]
                        }
                        service.spreadsheets().batchUpdate(spreadsheetId=ID_HOJA_CALCULO, body=body).execute()
                        print(f"[INFO] Se eliminó la inscripción de {row[1]} por falta de pago pasadas 24h.")
                except Exception as e:
                    pass
    except Exception as e:
        print(f"[ERROR LIMPIEZA INSCRIPCIONES]: {e}")

def alertas_citas_background():
    zona_mexico = pytz.timezone('America/Mexico_City')
    ahora_aware = datetime.datetime.now(zona_mexico)
    ahora_naive = ahora_aware.replace(tzinfo=None)
    
    try:
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        
        time_min = ahora_aware.isoformat()
        time_max = (ahora_aware + datetime.timedelta(hours=25)).isoformat()
        
        for especialista, cal_id in DIRECTORIO_CALENDARIOS.items():
            events_result = service.events().list(
                calendarId=cal_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            
            for event in events:
                start_str = event['start'].get('dateTime')
                if not start_str: 
                    continue
                
                hora_cita = datetime.datetime.fromisoformat(start_str.replace('Z', '+00:00')).astimezone(zona_mexico).replace(tzinfo=None)
                diferencia = hora_cita - ahora_naive
                
                desc = event.get('description', '')
                phone_match = re.search(r'Teléfono:\s*(\+?\d+)', desc)
                if not phone_match: 
                    continue
                telefono = phone_match.group(1)
                
                if datetime.timedelta(minutes=1425) <= diferencia <= datetime.timedelta(minutes=1440):
                    msg = f"🗓️ *Confirmación de Cita*\n\n¡Hola! Te escribimos de Inpulso 43 para confirmar tu cita de mañana a las {hora_cita.strftime('%H:%M')}. \n\n¿Podrías confirmarnos tu asistencia respondiendo a este mensaje? En caso de no poder asistir, te agradecemos mucho que nos avises para poder cederle el espacio a otro paciente en lista de espera. ✨"
                    enviar_mensaje_whatsapp(telefono, msg)
                    
                elif datetime.timedelta(minutes=110) <= diferencia <= datetime.timedelta(minutes=125):
                    ubicacion = ubicaciones_pacientes.get(telefono)
                    if ubicacion and API_KEY_MAPS:
                        try:
                            url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={ubicacion}&destinations=Av.+Hidalgo+533,Zapopan&departure_time=now&key={API_KEY_MAPS}"
                            res = requests.get(url).json()
                            if res['status'] == 'OK':
                                duracion_normal = res['rows'][0]['elements'][0]['duration']['value'] / 60
                                duracion_trafico = res['rows'][0]['elements'][0].get('duration_in_traffic', res['rows'][0]['elements'][0]['duration'])['value'] / 60
                                
                                if duracion_trafico > duracion_normal + 10:
                                    msg = f"🚗 *Alerta de Tráfico*\n¡Hola! Tu cita es en 2 horas. Detecté tráfico en tu ruta (aprox {int(duracion_trafico)} min). ¡Te sugiero salir con anticipación! ✨"
                                else:
                                    msg = f"🚗 *Recordatorio Inpulso*\n¡Hola! Tu cita es en 2 horas. El tráfico está fluido ({int(duracion_trafico)} min). ¡Te esperamos! 😊"
                                enviar_mensaje_whatsapp(telefono, msg)
                                continue
                        except:
                            pass
                            
                    msg = f"🚗 *Recordatorio Inpulso*\n¡Hola! Paso a recordarte que tu cita es en aprox 2 horas. Contempla el tiempo de estacionamiento (sujeto a un cajón disponible). ¡Te esperamos! ✨"
                    enviar_mensaje_whatsapp(telefono, msg)
                    
    except Exception as e:
        print(f"[ERROR ALERTAS BACKGROUND]: {e}")

def verificar_lista_espera_background():
    try:
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=creds)
        
        result = service.spreadsheets().values().get(spreadsheetId=ID_HOJA_CALCULO, range="Lista_Espera!A:F").execute()
        rows = result.get('values', [])
        
        for i, row in enumerate(rows):
            if len(row) >= 6 and row[5] == "PENDIENTE":
                nombre = row[1]
                telefono = row[2]
                especialista = row[3]
                fecha = row[4]
                
                disp = consultar_agenda(fecha, especialista)
                if "Espacios DISPONIBLES" in disp:
                    horarios_texto = disp.split("): ")[1] if "): " in disp else disp
                    msg = f"✨ ¡Hola {nombre}!\n\nTe escribo de Inpulso 43 porque se acaba de liberar un espacio con {especialista.title()} para el {fecha}. 🎉\n\nLos horarios que se abrieron son: {horarios_texto}\n\n¿Te gustaría aprovechar y agendar? Avísame pronto antes de que alguien más lo tome. 😊"
                    enviar_mensaje_whatsapp(telefono, msg)
                    
                    service.spreadsheets().values().update(
                        spreadsheetId=ID_HOJA_CALCULO,
                        range=f"Lista_Espera!F{i+1}",
                        valueInputOption="USER_ENTERED",
                        body={'values': [["NOTIFICADO"]]}
                    ).execute()
    except Exception as e:
        print(f"[ERROR EN LISTA DE ESPERA]: {e}")

scheduler = BackgroundScheduler(timezone="America/Mexico_City")
scheduler.add_job(func=alertas_citas_background, trigger="interval", minutes=15)
scheduler.add_job(func=verificar_lista_espera_background, trigger="interval", minutes=15)
scheduler.add_job(func=limpiar_inscripciones_pendientes_background, trigger="interval", minutes=60)
scheduler.start()

# ==========================================
# 4. EL PORTERO (RECIBE Y CONTESTA)
# ==========================================
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        challenge = request.args.get('hub.challenge')
        return challenge if challenge else "Servidor funcionando"

    if request.method == 'POST':
        datos = request.get_json()
        try:
            mensaje_info = datos['entry'][0]['changes'][0]['value']['messages'][0]
            mensaje_id = mensaje_info['id']
            
            if mensaje_id in mensajes_procesados:
                return "OK", 200
            
            mensajes_procesados.append(mensaje_id)
            if len(mensajes_procesados) > 500:
                mensajes_procesados.pop(0)

            numero_remitente = mensaje_info['from']
            tipo_mensaje = mensaje_info.get('type')
            
            zona_mexico = pytz.timezone('America/Mexico_City')
            hora_exacta = datetime.datetime.now(zona_mexico).strftime("%Y-%m-%d %H:%M")
            texto_contexto = f"[Sistema: Mensaje recibido el {hora_exacta}] "
            contenido_para_ia = None

            if tipo_mensaje == 'text':
                texto_paciente = mensaje_info['text']['body']
                contenido_para_ia = texto_contexto + texto_paciente
                
            elif tipo_mensaje == 'location':
                lat = mensaje_info['location']['latitude']
                lng = mensaje_info['location']['longitude']
                ubicaciones_pacientes[numero_remitente] = f"{lat},{lng}"
                contenido_para_ia = texto_contexto + f"[El paciente envió su ubicación {lat},{lng}]. Usa obtener_ruta_inpulso y responde el tiempo."
                
            elif tipo_mensaje in ['image', 'video', 'audio', 'voice', 'document']:
                tipo_clave = 'voice' if tipo_mensaje == 'voice' else tipo_mensaje
                media_id = mensaje_info[tipo_clave]['id']
                file_bytes, mime_type = descargar_media_whatsapp(media_id)

                if file_bytes:
                    caption = mensaje_info.get(tipo_clave, {}).get('caption', '')
                    texto_descriptivo = f"Archivo tipo {tipo_mensaje}. " + (f"Texto: {caption}" if caption else "")
                    
                    contenido_para_ia = [
                        types.Part(inline_data=types.Blob(data=file_bytes, mime_type=mime_type)),
                        types.Part(text=texto_contexto + texto_descriptivo + " [Nota del sistema: Evalúa minuciosamente si esta imagen corresponde a un comprobante de pago validando montos y cuentas según tus instrucciones].")
                    ]
                else:
                    contenido_para_ia = texto_contexto + f"Error al descargar archivo."
            else:
                return "OK", 200

            if contenido_para_ia:
                threading.Thread(target=procesar_mensaje_ia, args=(numero_remitente, contenido_para_ia)).start()
                
        except KeyError:
            pass
            
        return "OK", 200

if __name__ == '__main__':
    app.run(port=5000)