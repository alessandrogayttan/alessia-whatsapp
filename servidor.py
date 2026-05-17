import datetime
import pytz
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

# --- HERRAMIENTAS DE CALENDARIO ---
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

    fecha_hora = fecha_hora.replace(' ', 'T') 
    if len(fecha_hora) == 16: 
        fecha_hora += ":00"

    try:
        id_elegido = DIRECTORIO_CALENDARIOS[nombre_clave]
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)

        fecha_inicio = datetime.datetime.fromisoformat(fecha_hora)
        fecha_fin = fecha_inicio + datetime.timedelta(hours=1)

        event = {
            'summary': f'Cita {servicio}: {nombre_paciente}',
            'start': {'dateTime': fecha_inicio.isoformat(), 'timeZone': 'America/Mexico_City'},
            'end': {'dateTime': fecha_fin.isoformat(), 'timeZone': 'America/Mexico_City'},
        }
        service.events().insert(calendarId=id_elegido, body=event).execute()
        return f"Cita agendada con éxito con {nombre_clave} para el {fecha_hora}."
    
    except Exception as e:
        print(f"\n[ERROR DE CALENDARIO] No se pudo agendar: {e}\n")
        return f"Error técnico al agendar: {str(e)}. Pide disculpas al usuario e indícale que intente más tarde."

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
    direccion_clinica = "Av. Hidalgo 533, República, 45146 Zapopan, Jal." 
    origen = urllib.parse.quote(ubicacion_paciente)
    destino = urllib.parse.quote(direccion_clinica)
    link = f"https://www.google.com/maps/dir/?api=1&origin={origen}&destination={destino}"
    return f"Entrega este enlace de Google Maps al paciente para la ruta hacia Inpulso 43: {link}"

# --- NUEVA HERRAMIENTA: CÁLCULO DE GASOLINA ---
def calcular_gasto_combustible(vehiculo: str, kilometros: float, rendimiento_km_l: float):
    precio_gasolina_mxn = 24.50 
    litros_necesitados = kilometros / rendimiento_km_l
    costo_total = litros_necesitados * precio_gasolina_mxn
    return f"Para el vehículo {vehiculo} recorriendo {kilometros}km con rendimiento de {rendimiento_km_l} km/l, se consumirán aprox {litros_necesitados:.2f} litros. El costo estimado es de ${costo_total:.2f} MXN (calculado a ${precio_gasolina_mxn} por litro)."


# ==========================================
# 3. MEMORIA DE CHATS POR PACIENTE
# ==========================================
memoria_pacientes = {}

def obtener_chat_paciente(numero_telefono):
    if numero_telefono not in memoria_pacientes:
        print(f"Creando nuevo cerebro para el paciente: {numero_telefono}")
        
        zona_mexico = pytz.timezone('America/Mexico_City')
        hoy = datetime.datetime.now(zona_mexico)
        fecha_base = hoy.strftime("%Y-%m-%d")
        dias_semana = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        dia_actual = dias_semana[hoy.weekday()]
        
        instrucciones = f"""
Eres Alessia de Inpulso 43, una asistente inteligente, empática y capaz de pensar analíticamente. Hablas de forma natural, directa y profesional.
REGLA DE EMOJIS: Usa emojis sutilmente solo para saludar (ej. 👋) y despedirte o agradecer (ej. 🙏, 😊).

INFORMACIÓN CRÍTICA DEL SISTEMA:
- Hoy es {dia_actual}, la fecha base es {fecha_base}. (Se te informará la hora exacta en cada mensaje).
- DISPONIBILIDAD 24/7: Atiendes las 24 horas.
- HORARIO DE CITAS: Lunes a viernes, 7:00 am a 7:00 pm. NUNCA agendes en fines de semana ni días festivos oficiales. Si piden esos días, ofrece el siguiente día hábil.
- IDENTIDAD: Somos "Inpulso" o "Inpulso 43". Di "nuestra nutricionista" en lugar de "nutrición".
- FECHAS: Deduce la fecha a YYYY-MM-DD internamente.

--- CEREBRO DESBLOQUEADO Y CONTENCIÓN EMOCIONAL ---
Tienes acceso a todo tu conocimiento general. Si un paciente te cuenta sus problemas, expresa síntomas de estrés, ansiedad o dolor, o te hace preguntas generales, ESCÚCHALO Y AYÚDALO. Dale consejos prácticos (ej. ejercicios de respiración, validación emocional, información útil). Actúa como un apoyo real, aclarando sutilmente que no eres médico, pero invitándolo a agendar una sesión en Inpulso para tratarlo a fondo.

PASOS DE ATENCIÓN Y TRIAGE:
1. SALUDO INICIAL: Responde saludos de forma abierta ("¿En qué te puedo ayudar hoy en Inpulso?"). No asumas que quieren cita.
2. Si buscan cita, pregunta con quién (Juan, Sara, Patricia, Iván, nuestra nutricionista).
3. TALLERES Y MENTORAS: NO se agendan citas. Solo da información general.
4. Usa 'consultar_agenda' para revisar disponibilidad.
5. Usa 'agendar_cita' para fijar la hora.
6. PRE-CONSULTA (TRIAGE): INMEDIATAMENTE DESPUÉS de agendar exitosamente, dile al paciente: "Para que el especialista esté preparado, ¿podrías comentarme brevemente cuál es el motivo de tu visita?".
7. INDICACIONES DE PREPARACIÓN: Después de agendar, dale estas instrucciones vitales según el especialista:
   - Si es con la Nutricionista: "Recuerda venir con ropa cómoda y al menos 2 horas de ayuno."
   - Si es con Juan, Sara, Patricia o Iván: "Por favor llega 10 minutos antes de tu cita."
   - PARA TODOS: Agrega siempre: "Te recuerdo que contamos con lugares de estacionamiento sobre Av. Hidalgo o en calles aledañas."
8. Usa 'buscar_cita_paciente' para confirmar citas.
9. Usa 'obtener_ruta_inpulso' si envían ubicación.

FUNCIONES EXTRA:
- MÚSICA: Si expresan su estado de ánimo, recomienda 3 canciones con links exactos de búsqueda en Spotify y Apple Music.
- AUTOS: Conoces autos 2015-2026. Calcula costos de gasolina con la herramienta 'calcular_gasto_combustible'.
"""
        memoria_pacientes[numero_telefono] = client.chats.create(
            model='gemini-2.5-flash',
            config=types.GenerateContentConfig(
                system_instruction=instrucciones,
                tools=[consultar_agenda, agendar_cita, buscar_cita_paciente, obtener_ruta_inpulso, calcular_gasto_combustible]
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
            
            if tipo_mensaje == 'text':
                texto_paciente = mensaje_info['text']['body']
            elif tipo_mensaje == 'location':
                lat = mensaje_info['location']['latitude']
                lng = mensaje_info['location']['longitude']
                texto_paciente = f"Mi ubicación es {lat}, {lng}. ¿Cómo llego y a qué distancia estoy?"
            else:
                return "OK", 200 
            
            print(f"\n[WhatsApp] Paciente {numero_paciente} dice: {texto_paciente}")
            
            chat_alessia = obtener_chat_paciente(numero_paciente)
            
            zona_mexico = pytz.timezone('America/Mexico_City')
            hora_exacta = datetime.datetime.now(zona_mexico).strftime("%Y-%m-%d %H:%M")
            mensaje_con_contexto = f"[Sistema: Mensaje recibido el {hora_exacta}] {texto_paciente}"
            
            respuesta_ia = chat_alessia.send_message(mensaje_con_contexto)
            
            enviar_mensaje_whatsapp(numero_paciente, respuesta_ia.text)
            print(f"[WhatsApp] Alessia respondió: {respuesta_ia.text}")
            
        except KeyError:
            pass
            
        return "OK", 200

if __name__ == '__main__':
    print("ALESSIA ESTÁ VIVA Y ESCUCHANDO WHATSAPP EN EL PUERTO 5000")
    app.run(port=5000)