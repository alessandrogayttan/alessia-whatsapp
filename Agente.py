# DEPRECATED: Usa servidor.py como entrada principal.
import datetime
import json
import os

import requests
from dotenv import load_dotenv
from flask import Flask, request
from google import genai
from google.genai import types
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

app = Flask(__name__)

TOKEN_WHATSAPP = os.getenv("TOKEN_WHATSAPP", "")
ID_TELEFONO = os.getenv("ID_TELEFONO", "")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "agente-inpulso-bda72425fab5.json") 

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
    """Función para revisar qué horarios están ocupados en un día específico."""
    especialista = especialista.lower()
    if especialista not in DIRECTORIO_CALENDARIOS:
        return f"No tengo la agenda de {especialista}."
    
    id_elegido = DIRECTORIO_CALENDARIOS[especialista]
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    time_min = f"{fecha}T00:00:00-06:00"
    time_max = f"{fecha}T23:59:59-06:00"

    events_result = service.events().list(
        calendarId=id_elegido, timeMin=time_min, timeMax=time_max,
        singleEvents=True, orderBy='startTime').execute()
    events = events_result.get('items', [])

    if not events:
        return f"La agenda de {especialista} está completamente libre el {fecha}."
    
    ocupados = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        ocupados.append(f"De {start[11:16]} a {end[11:16]}")
        
    return f"El {fecha}, {especialista} tiene OCUPADO: " + ", ".join(ocupados) + ". Sugiere al paciente horarios libres."

def agendar_cita(servicio: str, fecha_hora: str, nombre_paciente: str, especialista: str):
    """Función para agendar la cita."""
    especialista = especialista.lower()
    id_elegido = DIRECTORIO_CALENDARIOS[especialista]
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    event = {
        'summary': f'Cita {servicio}: {nombre_paciente}',
        'start': {'dateTime': fecha_hora, 'timeZone': 'America/Mexico_City'},
        'end': {'dateTime': (datetime.datetime.fromisoformat(fecha_hora) + datetime.timedelta(hours=1)).isoformat(), 'timeZone': 'America/Mexico_City'},
    }
    service.events().insert(calendarId=id_elegido, body=event).execute()
    return f"¡Cita agendada con éxito para el {fecha_hora}!"

hoy = datetime.datetime.now()
fecha_actual = hoy.strftime("%Y-%m-%d")
dias_semana = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
dia_actual = dias_semana[hoy.weekday()]

instrucciones = f"""
Eres Alessia de Inpulso 43. Tu tono es cálido, empático y muy profesional (Español de México).
El horario de atención es de 9:00 am a 8:00 pm.
INFORMACIÓN CRÍTICA DEL SISTEMA:
- Hoy es {dia_actual}, fecha: {fecha_actual}. Usa esto como referencia absoluta si el paciente dice "hoy", "mañana", "el próximo lunes", etc.
- NUNCA le exijas al paciente un formato de fecha. Deja que hablen de forma natural. TÚ eres la Inteligencia Artificial, tú debes deducir y convertir la fecha a YYYY-MM-DD en tu mente antes de usar las herramientas.
Pasos para agendar:
1. Saluda y pide el nombre.
2. Pregunta con quién buscan la cita (Juan, Sara, Patricia, Iván, Nutrición, Mentoras o Talleres).
3. Si el paciente te pregunta por disponibilidad, usa la herramienta 'consultar_agenda'.
4. Con base en lo que te devuelva la herramienta, ofrécele al paciente opciones que estén LIBRES.
5. Cuando el paciente elija la hora, usa la herramienta 'agendar_cita'.
"""

# ==========================================
# 3. MEMORIA DE CHATS POR PACIENTE
# ==========================================
memoria_pacientes = {}

def obtener_chat_paciente(numero_telefono):
    """Crea un cerebro nuevo para un paciente, o recupera el que ya estaba usando."""
    if numero_telefono not in memoria_pacientes:
        print(f"Creando nuevo cerebro para el paciente: {numero_telefono}")
        memoria_pacientes[numero_telefono] = client.chats.create(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(
                system_instruction=instrucciones,
                tools=[consultar_agenda, agendar_cita]
            )
        )
    return memoria_pacientes[numero_telefono]

def enviar_mensaje_whatsapp(telefono_destino, texto):
    """Función que usa la tubería de Meta para contestar."""
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
            # Extraer los datos del mensaje que llegó
            mensaje_info = datos['entry'][0]['changes'][0]['value']['messages'][0]
            numero_paciente = mensaje_info['from']
            texto_paciente = mensaje_info['text']['body']
            
            print(f"\n[WhatsApp] Paciente {numero_paciente} dice: {texto_paciente}")
            
            # 1. Sacar el cerebro correspondiente a este paciente
            chat_alessia = obtener_chat_paciente(numero_paciente)
            
            # 2. Hacer que Alessia piense la respuesta (o use herramientas)
            print("Alessia está pensando...")
            respuesta_ia = chat_alessia.send_message(texto_paciente)
            
            # 3. Enviar la respuesta de vuelta a su celular
            enviar_mensaje_whatsapp(numero_paciente, respuesta_ia.text)
            print(f"[WhatsApp] Alessia respondió: {respuesta_ia.text}")
            
        except KeyError:
            # Si el JSON no trae mensaje (ej. es una notificación de "Leído"), lo ignoramos
            pass
            
        return "OK", 200

if __name__ == '__main__':
    print("¡ALESSIA 6.0 ESTÁ VIVA Y ESCUCHANDO WHATSAPP EN EL PUERTO 5000!")
    app.run(port=5000)