"""Chat web de Alessia — canal independiente de WhatsApp."""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from google import genai
from google.genai import types

import config
import storage
from observability import registrar_fallo_gemini
from tools import (
    agendar_cita,
    agregar_lista_espera,
    buscar_cita_paciente,
    calcular_gasto_combustible,
    cambiar_servicio_cita,
    cancelar_cita_paciente,
    consultar_agenda,
    consultar_mis_citas,
    consultar_precios_y_servicios,
    consultar_talleres_y_servicios,
    notificar_emergencia_paciente,
    obtener_contexto_citas_paciente,
    obtener_contexto_fecha_actual,
    obtener_contexto_perfil_paciente,
    obtener_ruta_inpulso,
    recordar_nombre_paciente,
    reagendar_cita_atomica,
    reagendar_cita_inteligente,
    registrar_escalacion_humana,
    registrar_interes_taller,
    registrar_paciente_taller,
    registrar_solicitud_facturacion,
    validar_fecha_cita,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "web-2026-07-02a"
_genai_client = None
_memoria_web: dict[str, object] = {}
_prompt_version_web: dict[str, str] = {}
_cerrojos_web: dict[str, threading.Lock] = {}

MENSAJE_RESCATE = (
    "Perdóname, tuve un pequeño tropiezo técnico 🙈 "
    "¿Me repites tu mensaje? Estoy aquí contigo."
)

_SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.I,
)


def _get_genai_client():
    global _genai_client
    if _genai_client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY no configurada")
        _genai_client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _genai_client


def _construir_instrucciones_web(
    session_id: str,
    telefono: str | None,
    nombre: str | None,
) -> str:
    banorte = config.CUENTAS_OFICIALES["BANORTE"]
    banamex = config.CUENTAS_OFICIALES["BANAMEX"]
    tel_ctx = telefono or "(aún no proporcionado — pídelo antes de agendar o inscribir)"
    wa = config.WHATSAPP_PACIENTES_URL or "WhatsApp de Inpulso 43"

    return f"""
Eres Alessia, de Inpulso 43. Atiendes el *chat en vivo* del sitio web {config.CLINICA_WEB_URL}
con el mismo cariño que recepción en persona. Este canal es la WEB, no WhatsApp.

IDENTIDAD (REGLA DE HIERRO):
- Preséntate solo como "Alessia, de Inpulso 43" o "Alessia de Inpulso".
- PROHIBIDO decir: asistente virtual, IA, inteligencia artificial, bot, automatizado, robot, modelo, Gemini.
- NUNCA te vuelvas a presentar si ya saludaste. Responde directo y con calidez.
- Usa emojis con naturalidad (😊 ✨ 💙 🌿).

CANAL WEB — REGLAS ESPECÍFICAS:
1. NO puedes recibir imágenes ni comprobantes de pago aquí. Si quieren confirmar un pago, enviar comprobante,
   recibir recibo automático, recordatorios de cita, escribir *MI CITA* o *HABLAR CON PERSONA*, invítalos con calidez
   a continuar por WhatsApp: {wa}
2. Antes de *agendar cita* o *inscribir a taller*, pide su número de WhatsApp (10 dígitos México) y nombre completo.
   Cuando los tengas, úsalos en las herramientas.
3. Teléfono del visitante en esta sesión: {tel_ctx}.
4. Nombre en sesión web: {nombre or "(aún no)"}.
5. ID de sesión interna (no lo menciones al usuario): {session_id}.

ORIENTACIÓN INICIAL (modelo 360° mente · cuerpo · propósito):
- Si no saben qué especialista necesitan, pregunta qué síntomas o motivo les trae ANTES de recomendar.
- Psicología → Sara Rosales. Nutrición → Gabriela Sánchez. Medicina → escalación a recepción (registrar_escalacion_humana).

INFORMACIÓN CLÍNICA Y WEB:
- Sitio: {config.CLINICA_WEB_URL} — talleres en /talleres.php, equipo en /nosotros.php.
- Ubicación: {config.CLINICA_DIRECCION} — Mapa: {config.CLINICA_MAPS_URL}
- Horario citas: lun–vie 7:00–19:00. Modalidad presencial y en línea (mentoras solo en línea).
- Pagos: efectivo/tarjeta en recepción; transferencia BANORTE CLABE {banorte['clabe']};
  con factura BANAMEX CLABE {banamex['clabe']}. Concepto: nombre completo del paciente.
- Citas online: pago total al confirmar (máx. 24 h antes). El terapeuta envía Zoom el día de la cita por WhatsApp.
- Cancelación con menos de 24 h: penalización 50%.

HERRAMIENTAS:
- Info talleres/precios: consultar_talleres_y_servicios, consultar_precios_y_servicios.
- Disponibilidad: consultar_agenda. Agendar: agendar_cita (teléfono obligatorio).
- Ver citas (si ya vinculó teléfono): consultar_mis_citas.
- Reagendar: reagendar_cita_inteligente → reagendar_cita_atomica.
- Inscripción taller: registrar_paciente_taller.
- Factura CFDI: registrar_solicitud_facturacion cuando tengas todos los datos.
- Emergencia: notificar_emergencia_paciente + indicar llamar al *911*.

TONO: cálida, 2–3 párrafos máximo. Sin presión al final ("¿te gustaría agendar?"). Sin despedidas hasta que el visitante se despida.
"""


def _herramientas_web():
    return [
        consultar_agenda,
        consultar_mis_citas,
        validar_fecha_cita,
        notificar_emergencia_paciente,
        agendar_cita,
        cancelar_cita_paciente,
        cambiar_servicio_cita,
        buscar_cita_paciente,
        obtener_ruta_inpulso,
        calcular_gasto_combustible,
        consultar_precios_y_servicios,
        consultar_talleres_y_servicios,
        registrar_paciente_taller,
        registrar_interes_taller,
        agregar_lista_espera,
        recordar_nombre_paciente,
        reagendar_cita_inteligente,
        reagendar_cita_atomica,
        registrar_solicitud_facturacion,
        registrar_escalacion_humana,
    ]


def _obtener_chat_web(session_id: str, telefono: str | None, nombre: str | None):
    clave = f"{session_id}:{PROMPT_VERSION}"
    if clave not in _memoria_web or _prompt_version_web.get(session_id) != PROMPT_VERSION:
        _memoria_web[clave] = _get_genai_client().chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=_construir_instrucciones_web(
                    session_id, telefono, nombre
                ),
                tools=_herramientas_web(),
            ),
        )
        _prompt_version_web[session_id] = PROMPT_VERSION
    return _memoria_web[clave]


def _gemini_send_message(chat, contenido, timeout: int = 120):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(chat.send_message, contenido)
        return future.result(timeout=timeout)


def _normalizar_telefono_mexico(texto: str) -> str | None:
    digits = re.sub(r"\D", "", texto)
    if len(digits) == 10:
        return "52" + digits
    if digits.startswith("521") and len(digits) == 13:
        return "52" + digits[3:]
    if digits.startswith("52") and len(digits) == 12:
        return digits
    return None


def _extraer_telefono_de_mensaje(texto: str) -> str | None:
    for candidato in re.findall(r"\+?[\d\s\-()]{10,18}", texto):
        normalizado = _normalizar_telefono_mexico(candidato)
        if normalizado:
            return normalizado
    return None


def _contexto_id_operaciones(telefono: str | None) -> str:
    if telefono:
        return telefono
    return ""


def envolver_mensaje_web(
    session_id: str,
    telefono: str | None,
    nombre: str | None,
    mensaje: str,
) -> str:
    ctx = obtener_contexto_fecha_actual()
    ctx += f"[Sistema: CANAL WEB — sesión {session_id}]\n"
    if nombre:
        ctx += f"[Sistema: Nombre en sesión web: {nombre}]\n"
    if telefono:
        ctx += obtener_contexto_perfil_paciente(telefono)
        ctx += obtener_contexto_citas_paciente(telefono)
    else:
        ctx += (
            "[Sistema: El visitante aún no ha dado su WhatsApp. "
            "Pídelo antes de agendar o inscribir a talleres.]\n"
        )
    return ctx + mensaje


def nueva_sesion_web() -> str:
    session_id = str(uuid.uuid4())
    storage.crear_sesion_web(session_id)
    return session_id


def sesion_valida(session_id: str) -> bool:
    return bool(_SESSION_ID_RE.match(session_id or ""))


def _vincular_telefono_si_aplica(session_id: str, mensaje: str, sesion: dict) -> str | None:
    telefono = sesion.get("telefono_vinculado")
    if telefono:
        return telefono
    detectado = _extraer_telefono_de_mensaje(mensaje)
    if detectado:
        storage.actualizar_sesion_web(session_id, telefono=detectado)
        return detectado
    return None


def procesar_mensaje_web(session_id: str, mensaje: str) -> str:
    if not config.ENABLE_WEB_CHAT:
        raise RuntimeError("Chat web desactivado")
    if not sesion_valida(session_id):
        raise ValueError("Sesión inválida")
    mensaje = (mensaje or "").strip()
    if not mensaje or len(mensaje) > 4000:
        raise ValueError("Mensaje inválido")

    sesion = storage.obtener_sesion_web(session_id)
    if not sesion:
        raise ValueError("Sesión no encontrada")

    telefono = _vincular_telefono_si_aplica(session_id, mensaje, sesion) or sesion.get(
        "telefono_vinculado"
    )
    nombre = sesion.get("nombre")
    if telefono and not sesion.get("telefono_vinculado"):
        sesion = storage.obtener_sesion_web(session_id) or sesion

    if session_id not in _cerrojos_web:
        _cerrojos_web[session_id] = threading.Lock()

    with _cerrojos_web[session_id]:
        import tools as tools_ctx

        id_ops = _contexto_id_operaciones(telefono) or f"web:{session_id}"
        tools_ctx._telefono_contexto = id_ops
        try:
            chat = _obtener_chat_web(session_id, telefono, nombre)
            contenido = envolver_mensaje_web(session_id, telefono, nombre, mensaje)
            for intento in range(2):
                try:
                    respuesta = _gemini_send_message(chat, contenido)
                    texto = (getattr(respuesta, "text", None) or "").strip()
                    if texto:
                        storage.actualizar_sesion_web(session_id)
                        return texto
                except FuturesTimeout:
                    logger.error("Timeout Gemini web %s intento %s", session_id, intento + 1)
                    registrar_fallo_gemini(f"web:{session_id}")
                    if intento == 0:
                        time.sleep(2)
                        continue
                except Exception as e:
                    logger.exception("Error Gemini web %s: %s", session_id, e)
                    registrar_fallo_gemini(f"web:{session_id}")
                    if intento == 0:
                        time.sleep(2)
                        continue
                    break
        finally:
            tools_ctx._telefono_contexto = None

    storage.actualizar_sesion_web(session_id)
    return MENSAJE_RESCATE


def hash_ip(ip: str) -> str:
    return hashlib.sha256(f"{ip}:web-chat".encode()).hexdigest()[:32]
