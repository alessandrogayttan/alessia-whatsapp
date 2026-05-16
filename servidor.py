import datetime
import requests
import json
import urllib.parse
from flask import Flask, request
from google import genai
from google.genai import types
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# ==========================================
# 1. TUS LLAVES DE WHATSAPP
# ==========================================
TOKEN_WHATSAPP = "EAA2QM4tKEQQBRcfuScb6qIzunBFoDjDx90ExeZCYXU1tO9PlvS2pHERnNmZB19pVXvYWuyVhwEPfr92JRQDGlsl8LlsnEC30pksZANEbS6fYnDEZBjCgDkzcYK8iHW4EKBWZBTZA2UZBf7XbY1WUCQ1ULmdDGj22vBqAttM1uP87RtNsgH7mipZB2N3eqiflrgZDZD"
ID_TELEFONO = "1090957250773198"

# ==========================================
# 2. CONFIGURACIÓN DEL CEREBRO DE ALESSIA
# ==========================================
client = genai.Client(api_key="AIzaSyC3G-vQPiGAYWEJoD-CFGLVJ_hsSbxVfGs")
SCOPES = ['https://www.googleapis.com/auth/calendar']
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

def consultar_agenda(fecha: str, especialista: str):
    especialista_completo = especialista.lower()
    nombre_clave = None
    
    # Buscar si alguna de nuestras palabras clave está dentro de lo que dijo la IA
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
        calendarId=id_elegido, timeMin=time_min, timeMax=time_max,
        singleEvents=True, orderBy='startTime').execute()
    events = events_result.get('items', [])

    if not events:
        return f"La agenda de {nombre_clave} está completamente libre el {fecha}."
    
    ocupados = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        ocupados.append(f"De {start[11:16]} a {end[11:16]}")
        
    return f"El {fecha}, {nombre_clave} tiene OCUPADO: " + ", ".join(ocupados) + ". Sugiere al paciente horarios libres."

def agendar_cita(servicio: str, fecha_hora: str, nombre_paciente: str, especialista: str):
    especialista_completo = especialista.lower()
    nombre_clave = None
    
    for nombre in DIRECTORIO_CALENDARIOS.keys():
        if nombre in especialista_completo:
            nombre_clave = nombre
            break
            
    if not nombre_clave:
        return f"No pude agendar porque no encontré al especialista: {especialista}."

    id_elegido = DIRECTORIO_CALENDARIOS[nombre_clave]
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    event = {
        'summary': f'Cita {servicio}: {nombre_paciente}',
        'start': {'dateTime': fecha_hora, 'timeZone': 'America/Mexico_City'},
        'end': {'dateTime': (datetime.datetime.fromisoformat(fecha_hora) + datetime.timedelta(hours=1)).isoformat(), 'timeZone': 'America/Mexico_City'},
    }
    service.events().insert(calendarId=id_elegido, body=event).execute()
    return f"Cita agendada con éxito con {nombre_clave} para el {fecha_hora}."

def buscar_cita_paciente(nombre_paciente: str, especialista: str):
    especialista_completo = especialista.lower()
    nombre_clave = None
    
    for nombre in DIRECTORIO_CALENDARIOS.keys():
        if nombre in especialista_completo:
            nombre_clave = nombre
            break
            
    if not nombre_clave:
        return f"No puedo buscar la cita porque no reconozco al especialista: {especialista}."

    id_elegido = DIRECTORIO_CALENDARIOS[nombre_clave]
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    hoy_utc = datetime.datetime.utcnow().isoformat() + 'Z'
    
    events_result = service.events().list(
        calendarId=id_elegido, timeMin=hoy_utc, maxResults=10,
        q=nombre_paciente, singleEvents=True, orderBy='startTime').execute()
    events = events_result.get('items', [])

    if not events:
        return f"No encontré ninguna cita para {nombre_paciente} con {nombre_clave}."

    citas_encontradas = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        fecha = start[:10]
        hora = start[11:16]
        citas_encontradas.append(f"El {fecha} a las {hora}")

    return f"Encontré estas citas para {nombre_paciente} con {nombre_clave}: " + ", ".join(citas_encontradas)

def obtener_ruta_inpulso(ubicacion_paciente: str):
    """Genera un link de Google Maps con la ruta hacia la clínica."""
    direccion_clinica = "Av. Hidalgo 533, República, 45146 Zapopan, Jal." 
    
    origen = urllib.parse.quote(ubicacion_paciente)
    destino = urllib.parse.quote(direccion_clinica)
    link = f"https://www.google.com/maps/dir/?api=1&origin={origen}&destination={destino}"
    
    return f"Entrega este enlace de Google Maps al paciente para que vea la distancia y la ruta hacia Inpulso 43: {link}"

hoy = datetime.datetime.now()
fecha_actual = hoy.strftime("%Y-%m-%d")
dias_semana = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
dia_actual = dias_semana[hoy.weekday()]

instrucciones = f"""
Eres Alessia de Inpulso 43. Tu tono es empático y muy profesional (Español de México).
El horario de atención es de 9:00 am a 8:00 pm.
INFORMACIÓN CRÍTICA DEL SISTEMA:
- Hoy es {dia_actual}, fecha: {fecha_actual}. Usa esto como referencia absoluta si el paciente dice "hoy", "mañana", "el próximo lunes", etc.
- NUNCA le exijas al paciente un formato de fecha. Deja que hablen de forma natural. TÚ eres la Inteligencia Artificial, tú debes deducir y convertir la fecha a YYYY-MM-DD en tu mente antes de usar las herramientas.
Pasos para agendar o asistir:
1. Saluda y pide el nombre.
2. Pregunta con quién buscan la cita o con quién la tienen agendada (Juan, Sara, Patricia, Iván, Nutrición, Mentoras o Talleres).
3. Si el paciente te pregunta por disponibilidad, usa la herramienta 'consultar_agenda'.
4. Con base en lo que te devuelva la herramienta, ofrécele al paciente opciones que estén LIBRES.
5. Cuando el paciente elija la hora, usa la herramienta 'agendar_cita'.
6. Si el paciente quiere CONFIRMAR o saber cuándo es su cita, usa la herramienta 'buscar_cita_paciente' con su nombre.
7. Si el paciente envía su ubicación, pregunta cómo llegar o pide la distancia, usa 'obtener_ruta_inpulso' pasándole su ubicación o coordenadas y entrégale el enlace.
"""

# ==========================================
# 3. MEMORIA DE CHATS POR PACIENTE
# ==========================================
memoria_pacientes = {}

def obtener_chat_paciente(numero_telefono):
    if numero_telefono not in memoria_pacientes:
        print(f"Creando nuevo cerebro para el paciente: {numero_telefono}")
        memoria_pacientes[numero_telefono] = client.chats.create(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(
                system_instruction=instrucciones,
                tools=[consultar_agenda, agendar_cita, buscar_cita_paciente, obtener_ruta_inpulso]
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
    respuesta = requests.post(url, headers=headers, data=json.dumps(data))
    
    if respuesta.status_code != 200:
        print(f"\nERROR DE META AL ENVIAR: {respuesta.text}")

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
            numero_paciente = mensaje_info['from']
            tipo_mensaje = mensaje_info.get('type')
            
            # Detecta si es texto normal o una ubicación GPS compartida
            if tipo_mensaje == 'text':
                texto_paciente = mensaje_info['text']['body']
            elif tipo_mensaje == 'location':
                lat = mensaje_info['location']['latitude']
                lng = mensaje_info['location']['longitude']
                texto_paciente = f"Mi ubicación es {lat}, {lng}. ¿Cómo llego y a qué distancia estoy?"
            else:
                return "OK", 200 # Ignora audios, stickers, imágenes, etc.
            
            print(f"\n[WhatsApp] Paciente {numero_paciente} dice: {texto_paciente}")
            
            chat_alessia = obtener_chat_paciente(numero_paciente)
            
            print("Alessia está pensando...")
            respuesta_ia = chat_alessia.send_message(texto_paciente)
            
            enviar_mensaje_whatsapp(numero_paciente, respuesta_ia.text)
            print(f"[WhatsApp] Alessia respondió: {respuesta_ia.text}")
            
        except KeyError:
            pass
            
        return "OK", 200

if __name__ == '__main__':
    print("ALESSIA 6.0 ESTÁ VIVA Y ESCUCHANDO WHATSAPP EN EL PUERTO 5000")
    app.run(port=5000)