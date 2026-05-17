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

# --- FUNCIÓN PARA DESCARGAR ARCHIVOS MULTIMEDIA DESDE META ---
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
        print(f"Error al descargar archivo multimedia de Meta: {e}")
    return None, None

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

        nombres_detallados = {
            "juan": "Juan",
            "sara": "Sara Rosales (Psicóloga)",
            "patricia": "Patricia",
            "ivan": "Iván",
            "nutricion": "nuestra Nutricionista"
        }
        especialista_texto = nombres_detallados.get(nombre_clave, especialista.title())

        event = {
            'summary': nombre_paciente.upper(),
            'description': f'Cita de {servicio} con {especialista_texto} en Inpulso.',
            'start': {'dateTime': fecha_inicio.isoformat(), 'timeZone': 'America/Mexico_City'},
            'end': {'dateTime': fecha_fin.isoformat(), 'timeZone': 'America/Mexico_City'},
        }
        service.events().insert(calendarId=id_elegido, body=event).execute()

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

        return f"Cita agendada con éxito. IMPORTANTE: Entrégale este enlace al paciente: {enlace_corto}"
    
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

# --- HERRAMIENTA: CÁLCULO DE GASOLINA ---
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
        
        dias_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        meses_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        dia_actual = dias_es[hoy.weekday()]
        
        calendario_contexto = ""
        for i in range(8):
            dia_f = hoy + datetime.timedelta(days=i)
            calendario_contexto += f"- {dias_es[dia_f.weekday()]} {dia_f.day} de {meses_es[dia_f.month - 1]} de {dia_f.year}\n"
        
        instrucciones = f"""
Eres Alessia, la asistente de Inpulso 43. Tu objetivo principal es que el paciente sienta que habla con una persona real, súper cálida, comprensiva y amable. Habla como si estuvieras chateando con un amigo de confianza por WhatsApp.

REGLAS DE ORO DE COMUNICACIÓN (SÉ MUY HUMANA):
1. EMPATÍA Y COMPRENSIÓN: Muestra comprensión activa. Si alguien te cuenta un problema, se siente mal o expresa estrés/ansiedad, valida sus emociones primero ("Siento mucho que estés pasando por eso...", "Entiendo perfecto cómo te sientes"). Sé un apoyo real y cálido.
2. EMOJIS AL ESTILO HUMANO: Usa emojis para expresar calidez y empatía de forma natural (ej. 😊, ✨, 🙌, 🫶, 🫂). No seas rígida, úsalos como lo haría alguien amable en WhatsApp.
3. NATURALIDAD: Usa expresiones humanas como "¡Claro que sí!", "Con mucho gusto", "No te preocupes". 
4. SÉ BREVE Y CONVERSACIONAL: Nadie quiere leer un robot dictando un manual. Mantén tus mensajes cortitos y al grano.
5. MÚSICA: Si recomiendas canciones, da 3 opciones diciendo solo el título y artista. PROHIBIDO poner enlaces o URLs.
6. FLUJO NATURAL: ¡PROHIBIDO preguntar de forma robótica "¿Hay algo más en lo que pueda ayudarte?" al final de tus mensajes! Deja que la plática fluya sola y si ya se resolvió la duda, despídete con cariño.

INFORMACIÓN CRÍTICA DEL SISTEMA:
- Hoy es {dia_actual}, la fecha base es {fecha_base}. 
- Calendario exacto de los próximos 7 días:
{calendario_contexto}
- Usa estrictamente las fechas de esa lista para agendar. Jamás las inventes.
- DISPONIBILIDAD: Atiendes 24/7.
- HORARIO DE CITAS: Lunes a viernes, 7:00 am a 7:00 pm. NUNCA agendes en fines de semana ni días festivos.
- IDENTIDAD: Somos "Inpulso". Di "nuestra nutricionista".
- UBICACIÓN EXACTA: Av. Hidalgo 533, República, 45146 Zapopan, Jalisco.

MULTIMODALIDAD (AUDIOS, FOTOS Y VIDEOS):
Tienes soporte completo para recibir archivos multimedia nativos. Si el usuario envía un mensaje de voz, foto o video, escúchalo o analízalo y responde directamente sobre eso con mucha empatía y naturalidad.

PASOS DE ATENCIÓN, TRIAGE Y FACTURACIÓN:
1. SALUDO INICIAL: Preséntate con mucha calidez (ej. "¡Hola! Soy Alessia, la asistente de Inpulso. ¿Cómo estás hoy? ¿En qué te puedo ayudar? 😊").
2. Si buscan cita, pregunta con quién (Juan, Sara, Patricia, Iván, nuestra nutricionista).
3. TALLERES Y MENTORAS: NO se agendan citas. Solo da información.
4. Usa 'consultar_agenda' para revisar disponibilidad.
5. Usa 'agendar_cita' para registrar el evento. Te devolverá un enlace corto (TinyURL).
6. INVITACIÓN AL CALENDARIO: Pásale el enlace corto diciendo algo como: "¡Súper! Tu cita ya quedó agendada. Aquí te dejo un link por si quieres guardarla en tu calendario con un solo clic: [link]".
7. PRE-CONSULTA (TRIAGE): En ese mismo mensaje, pregúntale con tacto: "Oye, y para que el especialista esté súper preparado, ¿me podrías platicar brevemente cuál es el motivo principal de tu visita? 🫶".
8. FACTURACIÓN: Antes de despedirte por completo, pregunta de manera natural si van a requerir factura (ej: "¿Vas a necesitar factura de tu sesión?"). Si dicen que sí, pídeles sus datos fiscales básicos (RFC, Razón Social, Régimen Fiscal, Código Postal, Uso de CFDI y Correo).
9. INDICACIONES DE LLEGADA: Al dar instrucciones finales. Nutricionista: ropa cómoda y 2 hrs ayuno. Psicólogos: llegar 10 mins antes. PARA TODOS: Aclara amablemente que en Inpulso hay un solo cajón de estacionamiento sujeto a disponibilidad, sugiriendo llegar con tiempo por si hay que buscar lugar cerca (Av. Hidalgo o calles aledañas).

AUTOS, DISTANCIAS Y RENDIMIENTO:
1. Si el paciente te dice de dónde viene, TÚ MISMA calcula la distancia estimada en kilómetros hasta Inpulso (Zapopan). No le preguntes la distancia.
2. TÚ MISMA estima el rendimiento en km/l según el coche (ej. RAV4 2018 aprox 11 km/l). No le preguntes cuánto rinde.
3. Con esos datos deducidos en tu mente, usa 'calcular_gasto_combustible' para entregarle la respuesta directa.
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
            
            zona_mexico = pytz.timezone('America/Mexico_City')
            hora_exacta = datetime.datetime.now(zona_mexico).strftime("%Y-%m-%d %H:%M")
            texto_contexto = f"[Sistema: Mensaje recibido el {hora_exacta}] "
            
            contenido_para_ia = None
            
            # --- MANEJO DE MENSAJES DE TEXTO ---
            if tipo_mensaje == 'text':
                texto_paciente = mensaje_info['text']['body']
                contenido_para_ia = texto_contexto + texto_paciente
                
            # --- MANEJO DE UBICACIONES ---
            elif tipo_mensaje == 'location':
                lat = mensaje_info['location']['latitude']
                lng = mensaje_info['location']['longitude']
                contenido_para_ia = texto_contexto + f"Mi ubicación es {lat}, {lng}. ¿Cómo llego y a qué distancia estoy?"
                
            # --- MANEJO DE MULTIMODALIDAD (AUDIOS, IMÁGENES Y VIDEOS) ---
            elif tipo_mensaje in ['image', 'video', 'audio', 'voice']:
                tipo_clave = 'voice' if tipo_mensaje == 'voice' else tipo_mensaje
                media_id = mensaje_info[tipo_clave]['id']
                
                print(f"[Sistema] Descargando archivo {tipo_mensaje} desde Meta...")
                file_bytes, mime_type = descargar_media_whatsapp(media_id)
                
                if file_bytes:
                    caption = mensaje_info.get(tipo_clave, {}).get('caption', '')
                    texto_descriptivo = f"El usuario envió un archivo de tipo {tipo_mensaje}. "
                    if caption:
                        texto_descriptivo += f"Texto adjunto por el usuario: {caption}"
                        
                    # Empaquetamos la media y el texto para mandárselos juntos a Gemini
                    part_media = types.Part(inline_data=types.Blob(data=file_bytes, mime_type=mime_type))
                    part_texto = types.Part(text=texto_contexto + texto_descriptivo)
                    contenido_para_ia = [part_media, part_texto]
                else:
                    contenido_para_ia = texto_contexto + f"El usuario intentó enviar un archivo {tipo_mensaje} pero hubo un error al obtenerlo del servidor."
            else:
                return "OK", 200 
            
            if contenido_para_ia is None:
                return "OK", 200
                
            print(f"\n[WhatsApp] Paciente {numero_paciente} dice: ({tipo_mensaje})")
            
            chat_alessia = obtener_chat_paciente(numero_paciente)
            respuesta_ia = chat_alessia.send_message(contenido_para_ia)
            
            enviar_mensaje_whatsapp(numero_paciente, respuesta_ia.text)
            print(f"[WhatsApp] Alessia respondió: {respuesta_ia.text}")
            
        except KeyError:
            pass
            
        return "OK", 200

if __name__ == '__main__':
    print("ALESSIA ESTÁ VIVA Y ESCUCHANDO WHATSAPP EN EL PUERTO 5000")
    app.run(port=5000)