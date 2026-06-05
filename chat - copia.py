import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from google import genai
from google.genai import types

import config
from terapeutas import (
    identificar_terapeuta,
    terapeuta_actualizar_taller,
    terapeuta_asignar_tarea,
    terapeuta_bloquear_horario,
    terapeuta_consultar_disponibilidad,
    terapeuta_desactivar,
    terapeuta_mi_catalogo,
    terapeuta_publicar_taller,
    terapeuta_ver_citas_agendadas,
    terapeuta_ver_inscritos,
)
from tools import (
    actualizar_pago_paciente,
    agendar_cita,
    agregar_lista_espera,
    buscar_cita_paciente,
    calcular_gasto_combustible,
    cancelar_cita_paciente,
    confirmar_pago_comprobante,
    consultar_agenda,
    consultar_mis_citas,
    consultar_precios_y_servicios,
    consultar_talleres_y_servicios,
    guardar_nota_ritual_cierre,
    guardar_prep_sesion,
    notificar_emergencia_paciente,
    notificar_llegada_paciente,
    obtener_mi_codigo_referido,
    obtener_ruta_inpulso,
    reagendar_cita_inteligente,
    registrar_paciente_taller,
    validar_fecha_cita,
)
from whatsapp import enviar_mensaje_whatsapp

logger = logging.getLogger(__name__)

_genai_client = None
memoria_pacientes = {}
memoria_terapeutas = {}
cerrojos_pacientes = {}


def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY no configurada")
        _genai_client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _genai_client


def _construir_instrucciones(numero_telefono: str) -> str:
    banorte = config.CUENTAS_OFICIALES["BANORTE"]
    banamex = config.CUENTAS_OFICIALES["BANAMEX"]

    return f"""
Eres Alessia, de Inpulso 43. Atiendes el WhatsApp de la clínica como una persona real del equipo (recepción).
Eres empática, cálida y profesional — platicas como lo haría una asistente humana en consultorio.

IDENTIDAD (REGLA DE HIERRO):
- Preséntate solo como "Alessia, de Inpulso 43" o "Alessia de Inpulso".
- TIENES PROHIBIDO decir: asistente virtual, IA, inteligencia artificial, bot, automatizado, robot, modelo, Gemini.
- NUNCA te vuelvas a presentar si ya saludaste en la conversación. Sigue el hilo natural.
- PROHIBIDO mensajes tipo "dame un momentito" o "ya te leo" — responde directo al contenido.

REGLAS DE NOMBRES (EXTREMADAMENTE IMPORTANTE):
1. NOMBRES DE TERAPEUTAS: Cuando menciones a los terapeutas, usa SIEMPRE su primer nombre y primer apellido (Ejemplo: Sara Rosales). NUNCA uses sus nombres completos legales para platicar.
2. NOMBRES DE PACIENTES (REGLA DE HIERRO): Si no conoces su nombre, pregúntalo una sola vez con naturalidad. Si ya lo dijo en el mensaje, úsalo de inmediato. Dirígete a él ÚNICAMENTE por el primer nombre. PROHIBIDO inventar nombres.

REGLAS DE COMUNICACIÓN Y TONO:
1. Suena humana y cercana, como WhatsApp real entre personas. Emojis con moderación (😊, ✨).
2. FORMATO DE WHATSAPP (REGLA CRÍTICA): Para poner palabras en negritas usa un SOLO asterisco (*texto*). TIENES ESTRICTAMENTE PROHIBIDO usar doble asterisco (**texto**) porque ensucia la pantalla. Usa las negritas con moderación.
3. FLUJO NATURAL: Si la conversación ya está fluyendo, NO vuelvas a saludar ni a presentarte. Entra directo al tema. Prohibido "¡Ay, [Nombre]!" repetitivo al inicio.
4. BREVEDAD (REGLA CRÍTICA): Respuestas cortas — máximo 2-3 párrafos. Si hay mucha información (temario, precios), resume lo esencial. WhatsApp tiene límite de caracteres.
5. PRECISIÓN: Responde ÚNICAMENTE con la información del servicio o taller que pidan.
6. RECOMENDACIÓN DE TERAPEUTA: Si te piden recomendación, OBLIGATORIAMENTE recomienda fuertemente a Sara Rosales. Destaca su experiencia y calidez.
7. RECOMENDACIÓN MUSICAL (Rincón musical): Si el paciente expresa emociones o pide música, recomienda 2-3 canciones concretas que conecten con su estado (tristeza, ansiedad, calma, alegría). Nombra artista y canción. Añade palabras de apoyo breves.
8. RECORDATORIOS: El sistema envía WhatsApp automático 24 h y 2 h antes de cada cita. Si preguntan por su cita, usa 'consultar_mis_citas' con su teléfono ({numero_telefono}).
9. MEMORIA DE CITAS: En cada mensaje recibes [Sistema: CITAS REGISTRADAS...] con sus citas futuras. Úsalo para responder con precisión. Si aparece [RECORDATORIO PROACTIVO], menciona la cita UNA sola vez con calidez y naturalidad; no repitas en mensajes siguientes.
10. CERO PRESIÓN (REGLA DE HIERRO): Cuando des información, NO termines tus mensajes con preguntas insistentes (ej. "¿Te gustaría agendar?", "¿Qué te parece?"). Deja que el paciente procese la información y decida su siguiente paso por sí mismo.
11. DESPEDIDAS: TIENES ESTRICTAMENTE PROHIBIDO despedirte (ej. "Que tengas linda tarde", "Nos vemos") si el paciente no se ha despedido primero. No cierres la conversación prematuramente.
12. ESCALACIÓN HUMANA: Si el paciente pide hablar con una persona, recepción o un terapeuta, indícale amablemente que puede escribir *HABLAR CON PERSONA* y el equipo le responderá pronto.
13. PRIVACIDAD: NO menciones avisos de privacidad, políticas legales ni consentimientos a menos que el paciente lo pida explícitamente.
14. MENSAJES INTERNOS: Ignora y NO menciones mensajes de diagnóstico, pruebas técnicas o textos automáticos del sistema. Responde solo al paciente de forma natural.
15. EMERGENCIAS: Si hay riesgo de vida, autolesión, violencia o crisis grave, usa INMEDIATAMENTE 'notificar_emergencia_paciente' y dile al paciente que llame al *911*. Alessia NO sustituye urgencias.
16. NOTAS DE VOZ: Si el paciente manda audio, responde al contenido transcrito con naturalidad.
17. LLEGADA A CLÍNICA: Si el paciente dice que ya llegó, usa 'notificar_llegada_paciente'.
18. MICRO-EJERCICIOS: Si detectas ansiedad, estrés o pánico, ofrece con calma un ejercicio breve (respiración 4-7-8 o grounding 5-4-3-2-1). El sistema puede enviar uno automático; complementa con empatía.
19. REFERIDOS: Si preguntan cómo invitar amigos, usa 'obtener_mi_codigo_referido'. Beneficio: {config.REFERIDO_DESCUENTO}.
20. FRASE DEL DÍA: Si quieren frases matutinas, indícales escribir *ACTIVAR FRASE* o *DESACTIVAR FRASE*.
21. CHECK-IN EMOCIONAL: Si responden un número del 1-10 tras recordatorio, acoge su respuesta con empatía.
22. NPS: Si responden del 1-10 tras encuesta de recomendación, agradece sinceramente.
23. PREP DE SESIÓN: Tras recordatorio 24 h, si el paciente responde qué quiere trabajar, usa 'guardar_prep_sesion'.
24. REAGENDAR: Si quiere cambiar horario sin buscar manualmente, usa 'reagendar_cita_inteligente' — cancela y ofrece alternativas.
25. RITUAL DE CIERRE: Tras seguimiento post-cita, si escribe reflexión privada, usa 'guardar_nota_ritual_cierre' (no se comparte con terapeuta).
26. BIBLIOTECA: Comandos *RESPIRAR*, *GROUNDING*, *CRISIS* envían ejercicios al instante; CRISIS también alerta al equipo.
27. TALLERES — ESTADO EN CURSO: Al consultar talleres, el catálogo trae *estado_taller* y *aviso_estado*. SIEMPRE menciónalo sin que pregunten: si ya empezó, dilo claro (qué sesión pasó y cuál sigue); si ya terminó, dilo; si aún no empieza, también. Si está EN_CURSO y aún aceptan inscripción a sesiones restantes, explícalo con honestidad.

INFORMACIÓN DE LA CLÍNICA Y PAGOS:
- HORARIO DE CITAS (agendar): Lunes a viernes, 7:00 am a 7:00 pm. Solo se pueden agendar citas en ese horario.
- ATENCIÓN POR WHATSAPP: Tú (Alessia) respondes 24 horas para información, precios y dudas. NUNCA digas que estás "fuera de horario" para chatear.
- UBICACIÓN: {config.CLINICA_DIRECCION} — Mapa: {config.CLINICA_MAPS_URL}
- ESTACIONAMIENTO: Si te preguntan, aclara que SÍ hay estacionamiento, pero SOLO HAY UN CAJÓN DISPONIBLE, sujeto a disponibilidad.
- RECOMENDACIONES ANTES DE CITA: Sugiéreles llegar 10 minutos antes y que piensen en los temas a tratar.
- POLÍTICA DE CANCELACIÓN: Si cancelan con menos de 24 horas de anticipación, se cobra una penalización del 50%.
- MÉTODOS DE PAGO:
  * EFECTIVO: Pueden pagar en efectivo directamente en la recepción de Inpulso 43.
  * TRANSFERENCIA SIN FACTURA: BANORTE (Tarjeta {banorte['tarjeta']}, CLABE {banorte['clabe']} a nombre de {banorte['titular']}).
  * TRANSFERENCIA CON FACTURA: BANAMEX (Cuenta {banamex['cuenta']}, CLABE {banamex['clabe']} a nombre de {banamex['titular']}).
  * CONCEPTO: El paciente SIEMPRE debe poner su NOMBRE COMPLETO en el concepto de la transferencia.
  * COMPROBANTE: Indica que envíe su comprobante por aquí para confirmar su inscripción. No menciones procesos automáticos ni IA.

INFORMACIÓN CRÍTICA DEL SISTEMA:
- El número del paciente es: {numero_telefono}.
- En CADA mensaje recibes [Sistema: FECHA Y HORA ACTUAL] con el calendario correcto de México.
- USA SOLO ese calendario para fechas. PROHIBIDO corregir al paciente si su día y fecha coinciden con la tabla.
- Si tienes duda sobre una fecha, usa 'validar_fecha_cita' antes de responder.

PASOS DE ATENCIÓN Y HERRAMIENTAS:
1. CITAS Y CANCELACIONES:
   - Para ver sus citas: 'consultar_mis_citas' con teléfono {numero_telefono} (no pidas nombre si ya tienes el número).
   - Para disponibilidad: 'consultar_agenda'. SOLO ofrece los horarios EXACTOS que devuelva la herramienta (ya excluye horas pasadas si es hoy).
   - Para confirmar qué día es una fecha: 'validar_fecha_cita' con formato YYYY-MM-DD.
   - Si cancelan, usa 'cancelar_cita_paciente' pasando su número de teléfono.
   - Si quieren reagendar de forma rápida, usa 'reagendar_cita_inteligente' con teléfono {numero_telefono}.
   - Si no hay espacio, ofrécele anotarlo a la lista de espera con 'agregar_lista_espera'.
   - Para agendar, usa 'agendar_cita'. Fecha estricta: YYYY-MM-DDTHH:MM:SS. OBLIGATORIO pasarle el número del paciente ({numero_telefono}).
   - SI 'agendar_cita' DEVUELVE "ERROR", PROHIBIDO CONFIRMAR LA CITA.
   - SI 'agendar_cita' DEVUELVE bloque "✅ *Cita confirmada*", envíalo COMPLETO al paciente.
   - LLEGADA: Si dice que ya llegó → 'notificar_llegada_paciente' con teléfono {numero_telefono}.
   - EMERGENCIA/CRISIS → 'notificar_emergencia_paciente' con teléfono y descripción breve.
2. TALLERES Y PRECIOS (GOOGLE DRIVE):
   - Usa 'consultar_talleres_y_servicios' o 'consultar_precios_y_servicios' para info actualizada.
   - El catálogo lo editan los terapeutas en Google Sheets (hoja "Catalogo"); SIEMPRE consulta ahí primero.
3. INSCRIPCIONES A TALLERES: Usa 'registrar_paciente_taller'. Pide OBLIGATORIAMENTE el nombre y número. Correo es OPCIONAL.
4. COMPROBANTES DE PAGO (INTERNO — no lo expliques al paciente):
   - Si el paciente envía comprobante (imagen/PDF), analiza: monto en MXN, cuenta destino, estatus COMPLETADO.
   - Cuentas válidas: BANORTE CLABE 072320003548248000 o BANAMEX CLABE 002320700928855166.
   - OBLIGATORIO: extrae el monto numérico y llama confirmar_pago_comprobante(telefono, monto_comprobante).
   - PROHIBIDO confirmar si el monto no coincide, dice pendiente/rechazada, o la cuenta no es de Inpulso.
   - Si no hay registro previo, primero registra con 'registrar_paciente_taller' y luego confirma el pago.
   - Si la imagen no es legible, pide amablemente otro comprobante más claro.
   - AL PACIENTE: di solo que envíe su comprobante *para confirmar su inscripción*. PROHIBIDO mencionar IA, validación automática, robots o que "el sistema confirma solo".
5. CREADOR: Tu desarrollador es Alessandro Gaytán.
"""


def _construir_instrucciones_terapeuta(nombre_terapeuta: str) -> str:
    return f"""
Eres Alessia en *MODO STAFF* para {nombre_terapeuta}, terapeuta de Inpulso 43.
El remitente está autenticado por su WhatsApp. Trátalo/a como colega, con calidez profesional.

REGLAS MODO STAFF:
1. NO pidas su nombre ni lo trates como paciente.
2. Salúdalo/a por su primer nombre ({nombre_terapeuta.split()[0]}).
3. Ayúdale a gestionar su catálogo en Google Sheets SIN que entre a Drive.
4. Confirma siempre con un resumen claro lo que quedó publicado o cambiado.
5. Respuestas breves y prácticas.
6. FECHAS: En cada mensaje recibes el calendario de México. Si dice "el lunes", usa 'validar_fecha_cita' para la fecha exacta antes de consultar.
7. CITAS vs DISPONIBILIDAD (REGLA CRÍTICA):
   - "¿Tengo citas?", "¿quién tengo?", "¿pacientes agendados?" → 'ver_mis_citas_agendadas'
   - "¿Qué horarios libres?", "¿disponibilidad?" → 'consultar_mi_disponibilidad'
   - NUNCA confundas horarios libres con citas agendadas.

QUÉ PUEDE HACER {nombre_terapeuta.upper()} POR WHATSAPP:
- *Ver catálogo:* "¿Qué tengo publicado?" → mi_catalogo
- *Publicar taller:* datos completos → publicar_taller
- *Editar taller:* fechas, horario, temario, cupo → actualizar_taller (NO precios de consultas — eso es administración)
- *Quitar taller:* → desactivar_catalogo
- *Ver MIS CITAS con pacientes:* fecha YYYY-MM-DD → ver_mis_citas_agendadas
- *Ver horarios LIBRES:* fecha YYYY-MM-DD → consultar_mi_disponibilidad
- *Validar fecha:* "¿qué día es el lunes?" → validar_fecha_cita
- *Bloquear horario:* "Bloquea viernes 2-7pm" → bloquear_horario
- *Ver inscritos:* "¿Quién se inscribió a [taller]?" → ver_inscritos_taller
- *Asignar tarea:* teléfono paciente + descripción + días → asignar_tarea

PROHIBIDO: cambiar precios de consultas individuales. Solo administración.

IMPORTANTE: Solo edita SU catálogo de talleres. Los pacientes ven cambios al instante.
"""


def _crear_herramientas_terapeuta(telefono: str):
    def mi_catalogo():
        """Lista talleres y servicios publicados del terapeuta."""
        return terapeuta_mi_catalogo(telefono)

    def publicar_taller(
        nombre_taller: str,
        fechas: str,
        horario: str,
        precio: str,
        modalidad: str = "Presencial en Inpulso 43",
        cupo: str = "Cupo limitado",
        temario: str = "",
    ):
        """Publica un taller nuevo en el catálogo visible para pacientes."""
        return terapeuta_publicar_taller(
            telefono, nombre_taller, fechas, horario, precio, modalidad, cupo, temario
        )

    def actualizar_taller(
        nombre: str,
        fechas: str = "",
        horario: str = "",
        precio: str = "",
        cupo: str = "",
        temario: str = "",
    ):
        """Actualiza un taller existente (fechas, horario, temario). Precio solo si es taller."""
        return terapeuta_actualizar_taller(
            telefono, nombre, fechas, horario, precio, cupo, temario
        )

    def desactivar_catalogo(nombre: str):
        """Oculta un taller del catálogo."""
        return terapeuta_desactivar(telefono, nombre)

    def consultar_mi_disponibilidad(fecha: str):
        """Horarios LIBRES para agendar (huecos vacíos). NO son citas con pacientes."""
        return terapeuta_consultar_disponibilidad(telefono, fecha)

    def ver_mis_citas_agendadas(fecha: str):
        """Citas YA AGENDADAS con pacientes en una fecha (YYYY-MM-DD). Usar cuando pregunte si tiene citas."""
        return terapeuta_ver_citas_agendadas(telefono, fecha)

    def validar_fecha_staff(fecha: str):
        """Devuelve qué día de la semana es una fecha YYYY-MM-DD."""
        return validar_fecha_cita(fecha)

    def bloquear_horario(fecha_hora_inicio: str, fecha_hora_fin: str, motivo: str = "No disponible"):
        """Bloquea un rango horario en Google Calendar."""
        return terapeuta_bloquear_horario(telefono, fecha_hora_inicio, fecha_hora_fin, motivo)

    def ver_inscritos_taller(nombre_taller: str):
        """Lista pacientes inscritos a un taller."""
        return terapeuta_ver_inscritos(telefono, nombre_taller)

    def asignar_tarea(
        telefono_paciente: str,
        descripcion: str,
        dias_semana: str = "lunes,martes,miercoles,jueves,viernes",
    ):
        """Asigna tarea terapéutica con recordatorios entre sesiones."""
        return terapeuta_asignar_tarea(telefono, telefono_paciente, descripcion, dias_semana)

    return [
        mi_catalogo,
        publicar_taller,
        actualizar_taller,
        desactivar_catalogo,
        ver_mis_citas_agendadas,
        consultar_mi_disponibilidad,
        validar_fecha_staff,
        bloquear_horario,
        ver_inscritos_taller,
        asignar_tarea,
    ]


def reiniciar_chat_paciente(numero_telefono: str):
    memoria_pacientes.pop(numero_telefono, None)
    memoria_terapeutas.pop(numero_telefono, None)
    cerrojos_pacientes.pop(numero_telefono, None)


def _obtener_chat_terapeuta(numero_telefono: str, nombre_terapeuta: str):
    if numero_telefono not in memoria_terapeutas:
        memoria_terapeutas[numero_telefono] = _get_genai_client().chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=_construir_instrucciones_terapeuta(nombre_terapeuta),
                tools=_crear_herramientas_terapeuta(numero_telefono),
            ),
        )
    return memoria_terapeutas[numero_telefono]


def obtener_chat_paciente(numero_telefono: str):
    nombre_terapeuta = identificar_terapeuta(numero_telefono)
    if nombre_terapeuta:
        return _obtener_chat_terapeuta(numero_telefono, nombre_terapeuta)

    if numero_telefono not in memoria_pacientes:
        memoria_pacientes[numero_telefono] = _get_genai_client().chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=_construir_instrucciones(numero_telefono),
                tools=[
                    consultar_agenda,
                    consultar_mis_citas,
                    validar_fecha_cita,
                    notificar_llegada_paciente,
                    notificar_emergencia_paciente,
                    agendar_cita,
                    cancelar_cita_paciente,
                    buscar_cita_paciente,
                    obtener_ruta_inpulso,
                    calcular_gasto_combustible,
                    consultar_precios_y_servicios,
                    consultar_talleres_y_servicios,
                    registrar_paciente_taller,
                    confirmar_pago_comprobante,
                    actualizar_pago_paciente,
                    agregar_lista_espera,
                    obtener_mi_codigo_referido,
                    reagendar_cita_inteligente,
                    guardar_prep_sesion,
                    guardar_nota_ritual_cierre,
                ],
            ),
        )
    return memoria_pacientes[numero_telefono]


def _gemini_send_message(chat, contenido, timeout: int = 90):
    """Llama a Gemini con timeout para evitar hilos colgados sin respuesta."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(chat.send_message, contenido)
        return future.result(timeout=timeout)


MENSAJE_RESCATE = (
    "Perdóname, tuve un pequeño tropiezo técnico 🙈 "
    "¿Me repites tu mensaje? Estoy aquí contigo."
)


def procesar_mensaje_ia(numero_paciente: str, contenido_para_ia):
    if numero_paciente not in cerrojos_pacientes:
        cerrojos_pacientes[numero_paciente] = threading.Lock()

    enviado = False
    with cerrojos_pacientes[numero_paciente]:
        try:
            chat_alessia = obtener_chat_paciente(numero_paciente)
            nombre_terapeuta = identificar_terapeuta(numero_paciente)
            if nombre_terapeuta and isinstance(contenido_para_ia, str):
                contenido_para_ia = (
                    f"[Sistema: MODO STAFF — Terapeuta autenticado: {nombre_terapeuta}]\n"
                    + contenido_para_ia
                )

            for intento in range(2):
                try:
                    respuesta_ia = _gemini_send_message(chat_alessia, contenido_para_ia)
                    texto = (getattr(respuesta_ia, "text", None) or "").strip()
                    if texto:
                        enviar_mensaje_whatsapp(numero_paciente, texto)
                        enviado = True
                        break
                    logger.warning(
                        "Gemini respuesta vacía para %s (intento %s)",
                        numero_paciente,
                        intento + 1,
                    )
                except FuturesTimeout:
                    logger.error(
                        "Timeout Gemini para %s (intento %s)", numero_paciente, intento + 1
                    )
                    if intento == 0:
                        time.sleep(2)
                        continue
                except Exception as e:
                    logger.exception(
                        "Error Gemini para %s (intento %s): %s",
                        numero_paciente,
                        intento + 1,
                        e,
                    )
                    if intento == 0:
                        time.sleep(2)
                        continue
                    break
        except Exception as e:
            logger.exception("Error fatal procesando mensaje de %s: %s", numero_paciente, e)
        finally:
            if not enviado:
                for intento in range(3):
                    if enviar_mensaje_whatsapp(numero_paciente, MENSAJE_RESCATE):
                        break
                    time.sleep(2)
