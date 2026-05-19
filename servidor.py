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
API_KEY_MAPS = "" 
ID_HOJA_CALCULO = "1HE-a6v2b-bCcN6JLHOJ3mevuRhJCWmInZEXkyV24L3k"

# Datos de cuentas oficiales para validación
CUENTAS_OFICIALES = {
    "SANTANDER": {
        "cuenta": "60604104279",
        "clabe": "014320606041042790",
        "titular": "Sara Verónica Rosales Delgado",
        "factura": False
    },
    "BANAMEX": {
        "cuenta": "70197775956",
        "clabe": "002320701977759567",
        "titular": "Inpulso 43 SC",
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
citas_pendientes = {} 

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
    
    events_result = service.events().list(
        calendarId=id_elegido, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    
    if not events:
        return f"La agenda de {nombre_clave} está libre el {fecha}."
    
    ocupados = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        ocupados.append(f"De {start[11:16]} a {end[11:16]}")
        
    return f"El {fecha}, {nombre_clave} tiene OCUPADO: " + ", ".join(ocupados)

def agendar_cita(servicio: str, fecha_hora: str, nombre_paciente: str, especialista: str, telefono_paciente: str = ""):
    especialista_completo = especialista.lower()
    nombre_clave = None
    
    for nombre in DIRECTORIO_CALENDARIOS.keys():
        if nombre in especialista_completo:
            nombre_clave = nombre
            break
            
    if not nombre_clave:
        return f"No pude agendar. Especialista no encontrado."

    fecha_hora = fecha_hora.replace(' ', 'T') 
    if len(fecha_hora) == 16:
        fecha_hora += ":00"

    try:
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
            'description': f'Cita de {servicio} con {especialista_texto}.',
            'start': {'dateTime': fecha_inicio.isoformat(), 'timeZone': 'America/Mexico_City'},
            'end': {'dateTime': fecha_fin.isoformat(), 'timeZone': 'America/Mexico_City'},
        }
        service.events().insert(calendarId=id_elegido, body=event).execute()
        
        if telefono_paciente:
            citas_pendientes[telefono_paciente] = fecha_inicio

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
            
        return f"Cita agendada. IMPORTANTE: Entrégale este enlace al paciente: {enlace_corto}"
    except Exception as e:
        return f"Error al agendar."

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
                distancia = elemento['distance']['text']
                duracion = elemento.get('duration_in_traffic', elemento['duration'])['text']
                return f"INSTRUCCIÓN PARA LA IA: Dile al paciente textualmente de forma muy natural que hará aproximadamente {duracion} de camino en auto hacia la clínica."
        except Exception as e:
            pass
            
    return "INSTRUCCIÓN PARA LA IA: Dile al paciente: 'Ya guardé tu ubicación. Considera el tráfico habitual para llegar a tiempo.'"

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

def registrar_paciente_taller(nombre: str, telefono: str, correo: str, nombre_taller: str):
    if not ID_HOJA_CALCULO:
        return "INSTRUCCIÓN PARA LA IA: Dile al paciente que no pudiste guardar sus datos."
        
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
        
        return "INSTRUCCIÓN PARA LA IA: Dile al paciente que sus datos han sido registrados con éxito."
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
        cleaned_target = telefono.replace("+", "").strip()
        
        for i in range(len(rows) - 1, -1, -1):
            if len(rows[i]) > 2:
                cleaned_row_phone = rows[i][2].replace("+", "").strip()
                if cleaned_target in cleaned_row_phone or cleaned_row_phone in cleaned_target:
                    row_index = i
                    break
                    
        if row_index is not None:
            colorear_celda_pago(service, sheet_id, row_index, estatus)
            return f"INSTRUCCIÓN PARA LA IA: Estatus actualizado a {estatus} para el teléfono {telefono}."
        else:
            return f"INSTRUCCIÓN PARA LA IA: No se encontró registro para el teléfono {telefono}."
    except Exception as e:
        return "INSTRUCCIÓN PARA LA IA: Fallo al actualizar la celda de color."

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

REGLAS DE COMUNICACIÓN:
1. SALUDO INICIAL (REGLA DE HIERRO): Si el paciente te saluda, SIEMPRE debes responder de forma extremadamente cálida, entusiasta y con emojis. NUNCA uses saludos secos.
2. PRECISIÓN ABSOLUTA (REGLA CRÍTICA): Si el paciente pregunta por el pago, la información o los detalles de un taller o servicio ESPECÍFICO, responde ÚNICAMENTE con la información de ese taller o servicio. ESTÁ ESTRICTAMENTE PROHIBIDO arrojar o mencionar los precios de otros especialistas, nutrióloga u otros servicios que el paciente NO haya pedido.
3. CIERRE NATURAL (REGLA CRÍTICA): ESTÁ ABSOLUTAMENTE PROHIBIDO usar frases de cierre como "¿Hay algo más en lo que pueda ayudarte?", "¿Puedo asistirte en algo más?", o cualquier variación robótica similar. Termina tu mensaje de forma natural, sin hacer preguntas de servicio al final.

INFORMACIÓN DE CUENTAS BANCARIAS:
- Si el paciente NO requiere factura, proporciónale la cuenta de SANTANDER: Cuenta 60604104279, CLABE 014320606041042790 a nombre de Sara Verónica Rosales Delgado.
- Si el paciente REQUIERE factura, indícale de forma muy clara que la ÚNICA cuenta autorizada es BANAMEX: Cuenta 70197775956, CLABE 002320701977759567 a nombre de Inpulso 43 SC.
- REGLA DE TRANSFERENCIA: Recuérdale siempre al paciente que en el concepto de la transferencia debe colocar obligatoriamente su NOMBRE COMPLETO.

INFORMACIÓN CRÍTICA DEL SISTEMA:
- Hoy es {dia_actual}, la fecha base es {fecha_base}. El número del paciente es: {numero_telefono}. Pásalo siempre a agendar_cita.
- Calendario exacto de los próximos 7 días:
{calendario_contexto}
- HORARIO DE CITAS: Lunes a viernes, 7:00 am a 7:00 pm. NUNCA agendes en fines de semana.

PASOS DE ATENCIÓN Y HERRAMIENTAS:
1. PRECIOS Y TALLERES: Si preguntan por costos o talleres, usa 'consultar_precios_y_servicios'.
2. INSCRIPCIONES A TALLERES: Si el paciente quiere inscribirse, pide su nombre, teléfono y correo. Ejecuta 'registrar_paciente_taller'.
3. SEGURIDAD DE PAGOS (REGLA CRÍTICA):
   - PROHIBIDO ejecutar 'actualizar_pago_paciente' si el usuario solo envía texto.
   - SOLO usa la herramienta si el paciente envía una IMAGEN del comprobante.
   - Valida en la imagen: Que el monto coincida con el servicio solicitado y que el destino sea alguna de nuestras dos cuentas oficiales (Santander: 60604104279 / Banamex: 70197775956).
4. CITA: Usa 'agendar_cita' y pásale el enlace corto.
5. UBICACIONES Y TRÁFICO: Cuando envíen ubicación, se ejecutará 'obtener_ruta_inpulso'.
6. LLEGADA: Si indica que "ya llegó", dile que en un momento salen a abrir.
7. CREADOR: Tu desarrollador es Alessandro Gaytán.
"""
        memoria_pacientes[numero_telefono] = client.chats.create(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(
                system_instruction=instrucciones,
                tools=[
                    consultar_agenda, 
                    agendar_cita, 
                    buscar_cita_paciente, 
                    obtener_ruta_inpulso, 
                    calcular_gasto_combustible, 
                    consultar_precios_y_servicios, 
                    registrar_paciente_taller, 
                    actualizar_pago_paciente
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
            mensaje_rescate = "Una disculpa, tuve un micro-corte en mi sistema de red. 😥 ¿Me podrías repetir tu último mensaje?"
            enviar_mensaje_whatsapp(numero_paciente, mensaje_rescate)

# ==========================================
# ALARMA DE TRÁFICO PROGRAMADA
# ==========================================
def monitoreo_trafico_background():
    zona_mexico = pytz.timezone('America/Mexico_City')
    ahora = datetime.datetime.now(zona_mexico)

    for telefono, hora_cita in list(citas_pendientes.items()):
        diferencia = hora_cita - ahora
        
        if datetime.timedelta(minutes=110) <= diferencia <= datetime.timedelta(minutes=125):
            ubicacion = ubicaciones_pacientes.get(telefono)
            if ubicacion:
                if API_KEY_MAPS:
                    try:
                        url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={ubicacion}&destinations=Av.+Hidalgo+533,Zapopan&departure_time=now&key={API_KEY_MAPS}"
                        res = requests.get(url).json()
                        if res['status'] == 'OK':
                            elemento = res['rows'][0]['elements'][0]
                            duracion_normal = elemento['duration']['value'] / 60
                            duracion_trafico = elemento.get('duration_in_traffic', elemento['duration'])['value'] / 60
                            
                            if duracion_trafico > duracion_normal + 10:
                                msg = f"🚗 *Alerta de Tráfico*\n¡Hola! Tu cita es en 2 horas. Detecté tráfico en tu ruta (aprox {int(duracion_trafico)} min). ¡Te sugiero salir con anticipación! ✨"
                            else:
                                msg = f"🚗 *Recordatorio Inpulso*\n¡Hola! Tu cita es en 2 horas. El tráfico está fluido ({int(duracion_trafico)} min). ¡Te esperamos! 🫶"
                            enviar_mensaje_whatsapp(telefono, msg)
                    except:
                        pass
                else:
                    enviar_mensaje_whatsapp(telefono, "🚗 *Recordatorio Inpulso*\n¡Hola! Paso a recordarte que tu cita es en aprox 2 horas. Contempla el tiempo de estacionamiento. ¡Te esperamos! ✨")
            else:
                enviar_mensaje_whatsapp(telefono, "🚗 *Recordatorio Inpulso*\n¡Hola! Paso a recordarte que tu cita es en aprox 2 horas. Contempla el tiempo de estacionamiento. ¡Te esperamos! ✨")
                
            del citas_pendientes[telefono]

scheduler = BackgroundScheduler(timezone="America/Mexico_City")
scheduler.add_job(func=monitoreo_trafico_background, trigger="interval", minutes=15)
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