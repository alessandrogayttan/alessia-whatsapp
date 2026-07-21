import datetime
import json
import logging
import re
import time
import urllib.parse
from pathlib import Path

import pytz
import requests

import config
import storage
from catalogo import consultar_catalogo_drive, obtener_cuentas_pago_texto, _leer_filas_catalogo
from google_client import (
    GoogleCalendarError,
    ejecutar_con_reintento,
    email_cuenta_servicio,
    get_calendar_service,
    get_sheets_service,
    reset_google_clients,
)

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)
PRECIOS_PATH = Path(__file__).resolve().parent / "precios.json"

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
DIAS_ES = [
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
]

_citas_cache: dict[str, dict] = {}
_agenda_cache: dict[str, dict] = {}
_telefono_contexto: str | None = None


def _formatear_fecha_español(fecha: datetime.datetime) -> str:
    dia = DIAS_ES[fecha.weekday()]
    mes = MESES_ES[fecha.month - 1]
    return f"{dia.capitalize()} {fecha.day} de {mes} de {fecha.year}"


def _es_servicio_online(servicio: str) -> bool:
    texto = (servicio or "").lower()
    return any(
        k in texto
        for k in ("online", "en línea", "en linea", "virtual", "zoom", "meet", "videollamada")
    )


def _construir_enlace_google_calendar(
    fecha_inicio: datetime.datetime,
    fecha_fin: datetime.datetime,
    especialista_texto: str,
    servicio: str,
    es_online: bool,
) -> str:
    format_start = fecha_inicio.strftime("%Y%m%dT%H%M%S")
    format_end = fecha_fin.strftime("%Y%m%dT%H%M%S")
    texto_link = urllib.parse.quote(f"Cita en Inpulso con {especialista_texto}")
    detalles = (
        f"Tu sesión online de {servicio} en Inpulso está confirmada."
        if es_online
        else f"Tu cita de {servicio} en Inpulso está confirmada."
    )
    detalles_link = urllib.parse.quote(detalles)
    ubicacion = (
        "Sesión online — Inpulso 43"
        if es_online
        else "Av. Hidalgo 533, República, 45146 Zapopan, Jal."
    )
    ubicacion_link = urllib.parse.quote(ubicacion)
    return (
        f"https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={texto_link}&dates={format_start}/{format_end}"
        f"&details={detalles_link}&location={ubicacion_link}&ctz=America/Mexico_City"
    )


def _texto_recomendaciones_online(especialista_texto: str) -> str:
    return (
        f"\n\n💻 *Recomendaciones para tu sesión en línea*\n"
        f"• Busca un lugar tranquilo y privado, con buena conexión 📶\n"
        f"• Audífonos ayudan mucho para escuchar y hablar con calma 🎧\n"
        f"• Ten agua cerca y silencia notificaciones que te distraigan\n"
        f"• Conéctate 5 minutos antes de tu hora\n"
        f"• *{especialista_texto}* te contactará *el día de tu cita* por aquí "
        f"con el link de Zoom para que te conectes ✨"
    )


def _texto_pago_online() -> str:
    banorte = config.CUENTAS_OFICIALES["BANORTE"]
    banamex = config.CUENTAS_OFICIALES["BANAMEX"]
    return (
        f"\n\n💳 *Pago de tu sesión online*\n"
        f"Para confirmar tu cita, el pago debe hacerse en su *totalidad* al confirmar "
        f"(a más tardar 24 horas antes de la sesión) 🙏\n\n"
        f"Puedes pagar con:\n"
        f"• Transferencia BANORTE (CLABE {banorte['clabe']})\n"
        f"• Transferencia BANAMEX (CLABE {banamex['clabe']})\n"
        f"• Efectivo o tarjeta en recepción de Inpulso 43 💳\n\n"
        f"Envía tu comprobante por aquí cuando lo tengas — con gusto te ayudamos 😊"
    )


def _formatear_confirmacion_cita(
    fecha_inicio: datetime.datetime,
    especialista_texto: str,
    servicio: str,
    *,
    es_online: bool = False,
) -> str:
    hora = fecha_inicio.strftime("%I:%M %p").lstrip("0").replace("AM", "a.m.").replace("PM", "p.m.")
    fecha_txt = _formatear_fecha_español(fecha_inicio)
    if es_online:
        cuerpo = (
            f"✅ *Cita confirmada*\n"
            f"💻 Sesión *en línea*\n"
            f"📅 {fecha_txt}, {hora}\n"
            f"👩‍⚕️ {especialista_texto}\n"
            f"🩺 {servicio}"
        )
        cuerpo += _texto_recomendaciones_online(especialista_texto)
        cuerpo += _texto_pago_online()
    else:
        cuerpo = (
            f"✅ *Cita confirmada*\n"
            f"📅 {fecha_txt}, {hora}\n"
            f"👩‍⚕️ {especialista_texto}\n"
            f"🩺 {servicio}\n"
            f"📍 {config.CLINICA_DIRECCION}\n"
            f"🗺️ {config.CLINICA_MAPS_URL}\n"
            f"💡 Llega 10 minutos antes 🌿"
        )
    return cuerpo + "\n\n📅 Toca el botón de abajo para agregarla a tu calendario 🙌"


def _extraer_montos_de_texto(texto: str) -> list[float]:
    montos = []
    for match in re.findall(r"\d[\d,]*\.?\d*", texto.replace(",", "")):
        try:
            valor = float(match)
            if valor >= 50:
                montos.append(valor)
        except ValueError:
            continue
    return montos


def _montos_esperados_taller(nombre_taller: str) -> list[float]:
    nombre_lower = nombre_taller.lower()
    for fila in _leer_filas_catalogo():
        if nombre_lower in fila["nombre"].lower() or fila["nombre"].lower() in nombre_lower:
            return _extraer_montos_de_texto(fila["precio"])
    return []


def _obtener_inscripcion_pendiente(telefono: str) -> dict | None:
    if not config.ID_HOJA_CALCULO:
        return None
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Inscripciones!A:F"
        ).execute()
        rows = result.get("values", [])
        target = _normalizar_telefono_digitos(telefono)
        for i in range(len(rows) - 1, 0, -1):
            row = rows[i]
            if len(row) < 6:
                continue
            row_digits = re.sub(r"\D", "", row[2])
            if target not in row_digits or row[5].upper() != "PENDIENTE":
                continue
            nombre_taller = row[4] if len(row) > 4 else ""
            return {
                "nombre": row[1] if len(row) > 1 else "",
                "telefono": row[2] if len(row) > 2 else telefono,
                "taller": nombre_taller,
                "montos_esperados": _montos_esperados_taller(nombre_taller),
            }
    except Exception as e:
        logger.error("Error leyendo inscripción pendiente: %s", e)
    return None


def validar_monto_pago(telefono: str, monto_comprobante: float) -> tuple[bool, str]:
    """Valida monto del comprobante contra inscripción pendiente y catálogo."""
    if monto_comprobante <= 0:
        return False, "El monto del comprobante debe ser mayor a cero."

    inscripcion = _obtener_inscripcion_pendiente(telefono)
    if not inscripcion:
        return False, (
            "No hay inscripción PENDIENTE para este teléfono. "
            "Primero registra al paciente con registrar_paciente_taller."
        )

    montos = inscripcion["montos_esperados"]
    if not montos:
        return True, (
            f"No hay precio en catálogo para '{inscripcion['taller']}'. "
            "Se acepta el pago; revisa manualmente el monto."
        )

    for esperado in montos:
        tolerancia = max(config.PAGO_TOLERANCIA_MXN, esperado * config.PAGO_TOLERANCIA_PORCENTAJE)
        if abs(monto_comprobante - esperado) <= tolerancia:
            return True, f"Monto ${monto_comprobante:.0f} coincide con precio esperado ${esperado:.0f}."

    montos_txt = ", ".join(f"${m:.0f}" for m in montos)
    return False, (
        f"Monto ${monto_comprobante:.0f} no coincide con precios esperados ({montos_txt}). "
        "Pide al paciente verificar el monto o enviar comprobante correcto."
    )


def _asegurar_hoja_escalaciones(service) -> bool:
    meta = service.spreadsheets().get(spreadsheetId=config.ID_HOJA_CALCULO).execute()
    tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if "Escalaciones" in tabs:
        return True
    service.spreadsheets().batchUpdate(
        spreadsheetId=config.ID_HOJA_CALCULO,
        body={"requests": [{"addSheet": {"properties": {"title": "Escalaciones"}}}]},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range="Escalaciones!A1:F1",
        valueInputOption="USER_ENTERED",
        body={"values": [["Fecha", "Teléfono", "Nombre", "Motivo", "Estado", "Notas"]]},
    ).execute()
    return True


def registrar_escalacion_humana(telefono: str, motivo: str = "Paciente solicitó hablar con persona"):
    """
    Registra escalación (Sheets + SQLite) y avisa a recepción por WhatsApp.
    El aviso a recepción NO depende de que Sheets funcione.
    """
    from whatsapp import enviar_recordatorio

    nombre = storage.obtener_nombre_paciente(telefono) or ""
    motivo_limpio = (motivo or "Paciente solicitó hablar con persona").strip()[:500]
    hoja_ok = False
    wa_ok = False
    destino = config.RECEPCION_WHATSAPP

    try:
        storage.guardar_escalacion_local(telefono, nombre, motivo_limpio)
    except Exception as e:
        logger.warning("No se pudo guardar escalación local: %s", e)

    if config.ID_HOJA_CALCULO:
        try:
            service = get_sheets_service()
            _asegurar_hoja_escalaciones(service)
            fecha = datetime.datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")
            service.spreadsheets().values().append(
                spreadsheetId=config.ID_HOJA_CALCULO,
                range="Escalaciones!A:F",
                valueInputOption="USER_ENTERED",
                body={"values": [[fecha, telefono, nombre, motivo_limpio, "PENDIENTE", ""]]},
            ).execute()
            hoja_ok = True
            logger.info("Escalación en Sheets: %s (%s)", telefono, nombre or "sin nombre")
        except Exception as e:
            logger.error("Error registrando escalación en Sheets: %s", e)
    else:
        logger.warning("Escalación sin ID_HOJA_CALCULO: %s", telefono)

    if destino:
        aviso = (
            f"🙋 *Escalación humana — Inpulso 43*\n\n"
            f"Tel: {telefono}\n"
            f"Nombre: {nombre or 'No registrado'}\n"
            f"Motivo: {motivo_limpio}\n\n"
            f"Responde a este paciente por WhatsApp lo antes posible."
        )
        params = [
            nombre or "Paciente",
            telefono[-10:] if len(telefono) >= 10 else telefono,
            motivo_limpio[:60],
        ]
        wa_ok = enviar_recordatorio(
            destino,
            aviso,
            config.WHATSAPP_TEMPLATE_ESCALACION,
            params if config.WHATSAPP_TEMPLATE_ESCALACION else None,
        )
        if wa_ok:
            logger.info("Escalación avisada a recepción %s", destino)
            try:
                storage.marcar_escalacion_notificada(telefono)
            except Exception:
                pass
        else:
            logger.error(
                "No se pudo avisar a recepción (%s) por WhatsApp. "
                "Revisa RECEPCION_WHATSAPP y ventana 24h / plantilla.",
                destino,
            )
    else:
        logger.error(
            "RECEPCION_WHATSAPP vacío: escalación de %s NO se envió a nadie. "
            "Configura el número en DigitalOcean.",
            telefono,
        )

    if wa_ok:
        return (
            "INSTRUCCIÓN PARA LA IA: Escalación registrada y recepción notificada. "
            "Dile al paciente con calidez que recepción fue avisada y le escribirán pronto "
            "por este mismo chat. NO digas que falló el sistema."
        )
    if destino:
        return (
            "INSTRUCCIÓN PARA LA IA: Registré la solicitud en el sistema, pero el aviso "
            "inmediato a recepción pudo fallar. Dile al paciente que el equipo revisará "
            "su mensaje y, si es urgente, marque *+52 33 1469 9772* o *+52 331 230 2221*."
        )
    return (
        "INSTRUCCIÓN PARA LA IA: No hay WhatsApp de recepción configurado. "
        "Pide disculpas breves y comparte *+52 33 1469 9772* y *+52 331 230 2221*."
    )


def escalar_a_recepcion(telefono: str, motivo: str = "Paciente solicitó hablar con persona") -> dict:
    """Ejecuta escalación y devuelve estado estructurado para el servidor."""
    mensaje = registrar_escalacion_humana(telefono, motivo)
    wa_ok = "recepción notificada" in mensaje.lower() or "recepcion notificada" in mensaje.lower()
    # También detectar éxito por frase "fue avisada"
    wa_ok = wa_ok or "fue avisada" in mensaje.lower()
    return {
        "whatsapp_ok": wa_ok,
        "recepcion_configurada": bool(config.RECEPCION_WHATSAPP),
        "mensaje_ia": mensaje,
    }


def _resolver_whatsapp_terapeuta(especialista: str) -> tuple[str, str] | None:
    """Devuelve (nombre_display, whatsapp) del terapeuta o None."""
    if not especialista:
        return None
    esp = especialista.lower().strip()
    for clave, numero in config.TERAPEUTAS_WHATSAPP.items():
        if clave in esp or esp in clave:
            display = NOMBRES_TERAPEUTAS.get(clave, especialista.title())
            if clave in NOMBRES_TERAPEUTAS:
                display = NOMBRES_TERAPEUTAS[clave]
            elif "sara" in clave:
                display = "Sara Rosales"
            return display, numero
    clave_cal = _resolver_especialista(especialista)
    if clave_cal and clave_cal in config.TERAPEUTAS_WHATSAPP:
        return NOMBRES_TERAPEUTAS.get(clave_cal, clave_cal.title()), config.TERAPEUTAS_WHATSAPP[clave_cal]
    return None


def _cita_relevante_hoy(telefono: str) -> dict | None:
    """Cita del paciente hoy, o la más próxima si no hay una hoy."""
    citas = listar_citas_futuras_por_telefono(telefono)
    if not citas:
        return None
    hoy = datetime.datetime.now(ZONA).strftime("%Y-%m-%d")
    for c in citas:
        if c["fecha"] == hoy:
            return c
    return citas[0]


def _inferir_terapeuta_paciente(telefono: str, especialista: str = "") -> tuple[str, str] | None:
    if especialista:
        res = _resolver_whatsapp_terapeuta(especialista)
        if res:
            return res
    cita = _cita_relevante_hoy(telefono)
    if cita:
        return _resolver_whatsapp_terapeuta(cita["especialista"])
    if config.TERAPEUTAS_WHATSAPP.get("sara"):
        return "Sara Rosales", config.TERAPEUTAS_WHATSAPP["sara"]
    return None


def notificar_llegada_paciente(telefono_paciente: str, especialista: str = ""):
    """
    Avisa al terapeuta por WhatsApp que su paciente llegó a Inpulso.
    Si no indicas especialista, se usa la cita de hoy o la más próxima.
    """
    from whatsapp import enviar_mensaje_whatsapp

    nombre = storage.obtener_nombre_paciente(telefono_paciente) or "Paciente"
    terapeuta_info = _inferir_terapeuta_paciente(telefono_paciente, especialista)
    if not terapeuta_info:
        return (
            "INSTRUCCIÓN PARA LA IA: No hay WhatsApp configurado para ese terapeuta. "
            "Dile al paciente que recepción ya fue avisada y que espere un momento."
        )

    display, whatsapp = terapeuta_info
    cita = _cita_relevante_hoy(telefono_paciente)
    cita_txt = ""
    if cita:
        cita_txt = f"\nCita: {cita['fecha']} {cita['hora']} — {cita['servicio']}"

    aviso = (
        f"🚪 *Paciente en recepción*\n"
        f"Paciente: {nombre}\n"
        f"Tel: {telefono_paciente}{cita_txt}\n\n"
        f"Te avisamos que ya llegó a Inpulso 43."
    )
    ok = enviar_mensaje_whatsapp(whatsapp, aviso)
    registrar_escalacion_humana(
        telefono_paciente,
        f"Llegada a clínica — aviso enviado a {display}",
    )
    if ok:
        return (
            f"ÉXITO: Aviso de llegada enviado a {display}. INSTRUCCIÓN PARA LA IA: "
            f"Confirma al paciente con calidez que {display} fue notificada y que lo "
            f"atiendan en breve. Recuérdale el cajón de estacionamiento si aplica."
        )
    return (
        f"INSTRUCCIÓN PARA LA IA: Intenté avisar a {display} pero WhatsApp no entregó el mensaje "
        f"(puede que no haya escrito a Alessia antes). Dile al paciente que espere en recepción."
    )


def notificar_emergencia_paciente(
    telefono_paciente: str,
    descripcion: str,
    especialista: str = "",
):
    """
    Avisa emergencia o crisis al terapeuta y recepción. Usar SOLO ante riesgo real.
    Siempre indica al paciente llamar al 911.
    """
    from whatsapp import enviar_mensaje_whatsapp

    nombre = storage.obtener_nombre_paciente(telefono_paciente) or "Paciente"
    terapeuta_info = _inferir_terapeuta_paciente(telefono_paciente, especialista)
    enviados = []

    aviso = (
        f"🚨 *EMERGENCIA / CRISIS*\n"
        f"Paciente: {nombre}\n"
        f"Tel: {telefono_paciente}\n"
        f"Detalle: {descripcion[:500]}\n\n"
        f"Contactar al paciente de inmediato. Si hay riesgo de vida, urgencias/911."
    )

    if terapeuta_info:
        display, whatsapp = terapeuta_info
        if enviar_mensaje_whatsapp(whatsapp, aviso):
            enviados.append(display)

    if config.RECEPCION_WHATSAPP:
        if enviar_mensaje_whatsapp(config.RECEPCION_WHATSAPP, aviso):
            enviados.append("recepción")

    registrar_escalacion_humana(
        telefono_paciente,
        f"EMERGENCIA: {descripcion[:200]}",
    )

    if enviados:
        return (
            f"ÉXITO: Emergencia notificada a {', '.join(enviados)}. INSTRUCCIÓN PARA LA IA: "
            f"Con mucha calma indica al paciente que llame al *911* si hay riesgo inmediato. "
            f"Confirma que el equipo ({', '.join(enviados)}) fue alertado y no está solo."
        )
    return (
        "INSTRUCCIÓN PARA LA IA: Registré la emergencia pero no pude enviar WhatsApp a terapeutas. "
        "Indica al paciente llamar al *911* de inmediato si hay riesgo de vida."
    )


def _resolver_especialista(especialista: str) -> str | None:
    especialista_completo = especialista.lower().strip()
    alias = {
        "gabriela": "nutricion",
        "gabriela sanchez": "nutricion",
        "gabriela sánchez": "nutricion",
        "nutricionista": "nutricion",
        "nutrición": "nutricion",
    }
    if especialista_completo in alias:
        return alias[especialista_completo]
    for clave_alias, destino in alias.items():
        if clave_alias in especialista_completo:
            return destino
    for nombre in config.DIRECTORIO_CALENDARIOS:
        if nombre in especialista_completo:
            return nombre
    return None


def _invalidar_cache_agenda(calendar_id: str | None = None, fecha: str | None = None):
    global _agenda_cache
    if calendar_id and fecha:
        _agenda_cache.pop(f"{calendar_id}:{fecha}", None)
        return
    if calendar_id:
        prefix = f"{calendar_id}:"
        for key in list(_agenda_cache):
            if key.startswith(prefix):
                _agenda_cache.pop(key, None)
        return
    _agenda_cache.clear()


def _respuesta_fallo_calendario(especialista: str, fecha: str, error: Exception) -> str:
    clave = _resolver_especialista(especialista) or especialista
    logger.error(
        "Calendario agotó reintentos automáticos (%s, %s): %s",
        clave,
        fecha,
        error,
    )
    return (
        "ERROR_CALENDARIO_TEMPORAL: La agenda no respondió tras varios intentos automáticos. "
        "INSTRUCCIÓN PARA LA IA: Di algo natural como que estás revisando la disponibilidad "
        "y vuelve a llamar consultar_agenda con la misma fecha y especialista de inmediato "
        "(hasta 3 veces en esta conversación). NO menciones errores técnicos ni sistemas. "
        "NO pidas al paciente repetir su mensaje."
    )


_health_calendario_cache: dict = {"ts": 0.0, "fallos": []}


def verificar_acceso_calendarios(*, rapido: bool = False) -> list[str]:
    """Prueba lectura de calendarios críticos. Devuelve lista de errores."""
    global _health_calendario_cache
    if rapido and time.time() - _health_calendario_cache["ts"] < 120:
        return list(_health_calendario_cache["fallos"])

    errores = []
    hoy = datetime.datetime.now(ZONA).strftime("%Y-%m-%d")
    cuenta = email_cuenta_servicio()
    max_wait = 4 if rapido else config.CALENDAR_MAX_WAIT_BACKGROUND_SECONDS
    for nombre in config.CALENDARIOS_CRITICOS:
        calendar_id = config.DIRECTORIO_CALENDARIOS.get(nombre)
        if not calendar_id:
            errores.append(f"calendar:{nombre} (sin ID configurado)")
            continue
        try:
            _obtener_eventos_dia(
                calendar_id,
                hoy,
                usar_cache=not rapido,
                max_wait_seconds=max_wait,
            )
        except GoogleCalendarError as e:
            hint = (
                f" Comparte el calendario con {cuenta} como Editor."
                if cuenta and e.http_status == 403
                else ""
            )
            errores.append(f"calendar:{nombre} ({e.http_status or 'error'}){hint}")
        except Exception as e:
            errores.append(f"calendar:{nombre} ({type(e).__name__})")

    if rapido:
        _health_calendario_cache = {"ts": time.time(), "fallos": errores}
    return errores


def estado_calendarios_cache() -> list[str]:
    """Devuelve fallos de calendario cacheados (sin llamar a Google)."""
    fallos = _health_calendario_cache.get("fallos", [])
    if not fallos:
        return []
    ts = _health_calendario_cache.get("ts", 0)
    if time.time() - ts > 600:
        return ["Calendario: sin verificación reciente (keepalive pendiente)"]
    return [f"Calendario: {f}" for f in fallos]


def _obtener_eventos_dia(
    calendar_id: str,
    fecha: str,
    *,
    usar_cache: bool = True,
    max_wait_seconds: float | None = None,
):
    """Lee eventos del día con reintentos automáticos acotados en tiempo."""
    cache_key = f"{calendar_id}:{fecha}"
    ultimo_error: Exception | None = None
    ciclos = config.CALENDAR_CONSULTA_REINTENTOS
    max_wait = (
        max_wait_seconds
        if max_wait_seconds is not None
        else config.CALENDAR_MAX_WAIT_SECONDS
    )
    deadline = time.monotonic() + max_wait

    for ciclo in range(ciclos):
        if time.monotonic() >= deadline:
            break
        if usar_cache and ciclo == 0:
            hit = _agenda_cache.get(cache_key)
            if hit and time.time() - hit["ts"] < config.CITAS_CACHE_TTL:
                return hit["items"]

        time_min = f"{fecha}T00:00:00-06:00"
        time_max = f"{fecha}T23:59:59-06:00"

        def _listar():
            service = get_calendar_service()
            return (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

        try:
            events_result = ejecutar_con_reintento(
                _listar,
                f"calendar.list {calendar_id} {fecha}",
                deadline=deadline,
            )
            items = events_result.get("items", [])
            _agenda_cache[cache_key] = {"items": items, "ts": time.time()}
            if ciclo > 0:
                logger.info(
                    "Calendario recuperado en ciclo %s/%s: %s %s",
                    ciclo + 1,
                    ciclos,
                    calendar_id,
                    fecha,
                )
            return items
        except (GoogleCalendarError, Exception) as e:
            ultimo_error = e
            _invalidar_cache_agenda(calendar_id, fecha)
            reset_google_clients()
            status = getattr(e, "http_status", None)
            logger.warning(
                "Calendario %s %s — ciclo %s/%s falló: %s",
                calendar_id,
                fecha,
                ciclo + 1,
                ciclos,
                e,
            )
            if status in (401, 403, 404):
                break
            if ciclo < ciclos - 1 and time.monotonic() < deadline:
                pausa = min(
                    config.CALENDAR_RETRY_PAUSE_SECONDS * (ciclo + 1),
                    max(0.5, deadline - time.monotonic()),
                )
                if pausa > 0:
                    time.sleep(pausa)

    if isinstance(ultimo_error, GoogleCalendarError):
        raise ultimo_error
    raise GoogleCalendarError(
        f"Calendario no disponible en {max_wait:.0f}s: {ultimo_error}",
        reason=str(ultimo_error) if ultimo_error else "timeout",
    ) from ultimo_error


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

    ahora = datetime.datetime.now(ZONA).replace(tzinfo=None)
    if slot_inicio < ahora.replace(minute=0, second=0, microsecond=0):
        return False

    slot_fin = slot_inicio + datetime.timedelta(hours=1)
    for o_start, o_end in ocupados:
        if max(slot_inicio, o_start) < min(slot_fin, o_end):
            return False
    return True


def consultar_precios_y_servicios(especialista: str = "todos"):
    """Consulta precios: Drive + inpulso43.com, catálogo web o precios.json local."""
    from catalogo import _leer_filas_catalogo

    if _leer_filas_catalogo():
        return consultar_catalogo_drive(especialista)

    from catalogo_web import contexto_web_para_ia, filas_catalogo_dict

    filas = filas_catalogo_dict()
    if filas:
        instruccion = (
            f"INSTRUCCIÓN PARA LA IA: {contexto_web_para_ia()} "
            "Todas las consultas y talleres (excepto mentoras) son presencial Y online."
        )
        esp_lower = especialista.lower()
        if esp_lower != "todos":
            filtradas = [
                f
                for f in filas
                if esp_lower in f["terapeuta"].lower() or esp_lower in f["nombre"].lower()
            ]
            if filtradas:
                return instruccion + " Catálogo: " + json.dumps(filtradas, ensure_ascii=False)
        return instruccion + " Catálogo: " + json.dumps(filas, ensure_ascii=False)

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


def consultar_talleres_y_servicios(especialista: str = "todos"):
    """Alias explícito para catálogo en Google Sheets (Drive)."""
    return consultar_catalogo_drive(especialista)


def consultar_sitio_inpulso(consulta: str, pagina: str = "auto") -> str:
    """Lee inpulso43.com en vivo (página oficial) según la pregunta del paciente."""
    from inpulso_web_live import consultar_sitio_inpulso as _consultar

    return _consultar(consulta, pagina)


def buscar_conocimiento_inpulso(consulta: str) -> str:
    """Busca en el índice RAG del sitio oficial y PDFs públicos de Inpulso."""
    from inpulso_rag import buscar_conocimiento_inpulso as _buscar

    return _buscar(consulta)


def _pista_texto_desde_contenido(contenido) -> str:
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        partes = []
        for parte in contenido:
            texto = getattr(parte, "text", None)
            if texto:
                partes.append(str(texto))
        return " ".join(partes)
    return ""


def _inicio_slots_disponibles(base_date: datetime.datetime) -> datetime.datetime:
    """Primera hora ofrecible: 7:00 am, o la hora actual si la fecha es hoy."""
    inicio_dia = base_date.replace(hour=7, minute=0, second=0, microsecond=0)
    ahora = datetime.datetime.now(ZONA).replace(tzinfo=None)
    if base_date.date() != ahora.date():
        return inicio_dia
    if ahora.minute > 0 or ahora.second > 0:
        desde_ahora = ahora.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
    else:
        desde_ahora = ahora.replace(minute=0, second=0, microsecond=0)
    return max(inicio_dia, desde_ahora)


def validar_fecha_cita(fecha: str):
    """
    Devuelve el día de la semana de una fecha (YYYY-MM-DD).
    Usar SIEMPRE antes de decirle al paciente que se equivocó en una fecha.
    """
    try:
        d = datetime.datetime.strptime(fecha.strip()[:10], "%Y-%m-%d")
    except ValueError:
        return "Formato inválido. La fecha debe ser YYYY-MM-DD."
    dia = DIAS_ES[d.weekday()]
    mes = MESES_ES[d.month - 1]
    return f"{fecha[:10]} es {dia} {d.day} de {mes} de {d.year}."


def obtener_contexto_fecha_actual() -> str:
    """Calendario fresco en cada mensaje (evita fechas desactualizadas en memoria del chat)."""
    hoy = datetime.datetime.now(ZONA)
    lineas = [
        "[Sistema: FECHA Y HORA ACTUAL — Zona México]",
        (
            f"Ahora: {DIAS_ES[hoy.weekday()]} {hoy.day} de {MESES_ES[hoy.month - 1]} "
            f"de {hoy.year} ({hoy.strftime('%Y-%m-%d')}) — {hoy.strftime('%H:%M')}"
        ),
        "Calendario (referencia obligatoria; NO adivines ni corrijas fechas sin esto):",
    ]
    for i in range(14):
        d = hoy + datetime.timedelta(days=i)
        lineas.append(
            f"  {d.strftime('%Y-%m-%d')} = {DIAS_ES[d.weekday()]} {d.day} de {MESES_ES[d.month - 1]}"
        )
    lineas.append(
        "REGLA: Si el paciente nombra un día que COINCIDE con esta tabla, ACEPTA su fecha. "
        "PROHIBIDO decirle que se equivoca si coincide. Usa 'validar_fecha_cita' si tienes duda."
    )
    return "\n".join(lineas) + "\n"


def consultar_agenda(fecha: str, especialista: str):
    nombre_clave = _resolver_especialista(especialista)
    if not nombre_clave:
        return f"No tengo la agenda de {especialista}."

    try:
        base_date = datetime.datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        return "Error: La fecha debe estar en formato exacto YYYY-MM-DD."

    calendar_id = config.DIRECTORIO_CALENDARIOS[nombre_clave]
    try:
        events = _obtener_eventos_dia(calendar_id, fecha)
    except (GoogleCalendarError, Exception) as e:
        return _respuesta_fallo_calendario(especialista, fecha, e)

    ocupados, dia_bloqueado = _parsear_ocupados(events, base_date)
    if dia_bloqueado:
        return f"El {fecha}, {nombre_clave} tiene bloqueado todo el día."

    horarios_disponibles = []
    slot_actual = _inicio_slots_disponibles(base_date)
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

    hoy_str = datetime.datetime.now(ZONA).strftime("%Y-%m-%d")
    sufijo = " (desde la hora actual en adelante)" if fecha == hoy_str else ""
    return (
        f"Espacios DISPONIBLES para {nombre_clave} el {fecha}{sufijo} (Citas de 1 hora): "
        + ", ".join(horarios_disponibles)
    )


def _es_evento_bloqueo(event: dict) -> bool:
    summary = (event.get("summary") or "").upper()
    if summary.startswith("BLOQUEADO"):
        return True
    if event.get("start", {}).get("date") and not event.get("start", {}).get("dateTime"):
        return True
    return False


def _formatear_evento_cita(event: dict) -> str:
    start_str = event["start"].get("dateTime") or event["start"].get("date", "")
    if "T" in start_str:
        hora = (
            datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            .astimezone(ZONA)
            .strftime("%H:%M")
        )
    else:
        hora = "Todo el día"

    paciente = event.get("summary", "Sin nombre").strip()
    desc = event.get("description", "")
    servicio = _parsear_servicio_descripcion(desc) if desc else "Consulta"
    phone_match = re.search(r"Teléfono:\s*(\+?\d+)", desc)
    tel = phone_match.group(1) if phone_match else "sin teléfono"
    return f"{hora} — {paciente} ({servicio}) — Tel: {tel}"


def listar_citas_agendadas_dia(especialista: str, fecha: str) -> str:
    """
    Lista las citas YA AGENDADAS (pacientes confirmados) de un terapeuta en una fecha.
    NO confundir con horarios disponibles — usar consultar_agenda para huecos libres.
    """
    nombre_clave = _resolver_especialista(especialista)
    if not nombre_clave:
        return f"No tengo calendario de {especialista}."

    try:
        datetime.datetime.strptime(fecha.strip()[:10], "%Y-%m-%d")
    except ValueError:
        return "ERROR: La fecha debe ser YYYY-MM-DD."

    fecha = fecha.strip()[:10]
    calendar_id = config.DIRECTORIO_CALENDARIOS[nombre_clave]
    try:
        events = _obtener_eventos_dia(calendar_id, fecha)
    except (GoogleCalendarError, Exception) as e:
        return _respuesta_fallo_calendario(especialista, fecha, e)

    citas = [e for e in events if not _es_evento_bloqueo(e)]

    display = NOMBRES_TERAPEUTAS.get(nombre_clave, especialista.title())
    dia_txt = validar_fecha_cita(fecha)

    if not citas:
        return (
            f"CITAS AGENDADAS de {display} el {fecha} ({dia_txt}): "
            f"NINGUNA — no tienes pacientes agendados ese día."
        )

    lineas = [f"CITAS AGENDADAS de {display} el {fecha} ({dia_txt}):"]
    for event in citas:
        lineas.append(f"- {_formatear_evento_cita(event)}")
    lineas.append(
        f"Total: {len(citas)} cita(s). INSTRUCCIÓN: Esto son citas confirmadas, "
        "NO horarios libres."
    )
    return "\n".join(lineas)


def _normalizar_telefono_digitos(telefono: str) -> str:
    target_digits = re.sub(r"\D", "", telefono)
    if target_digits.startswith("521") and len(target_digits) == 13:
        target_digits = target_digits.replace("521", "52", 1)
    return target_digits[-10:] if len(target_digits) >= 10 else target_digits


def _invalidar_cache_citas(telefono: str):
    digits = _normalizar_telefono_digitos(telefono)
    keys = [k for k in _citas_cache if k.endswith(digits) or k == digits]
    for k in keys:
        _citas_cache.pop(k, None)


NOMBRES_TERAPEUTAS = {
    "juan": "Juan Rosales",
    "sara": "Sara Rosales",
    "patricia": "Paty Velázquez",
    "ivan": "Ivan Navarro",
    "nutricion": "Gabriela Sánchez",
    "mentoras": "Mentoras",
    "talleres": "Talleres",
}


def _especialista_desde_calendario(calendar_id: str) -> str:
    for clave, cal_id in config.DIRECTORIO_CALENDARIOS.items():
        if cal_id == calendar_id:
            return NOMBRES_TERAPEUTAS.get(clave, clave.title())
    return "Especialista"


def _parsear_servicio_descripcion(descripcion: str) -> str:
    for prefijo in ("Cita ONLINE de ", "Cita de "):
        if descripcion.startswith(prefijo):
            parte = descripcion.split(" con ", 1)[0]
            return parte.replace(prefijo, "").strip()
    return "Consulta"


def _normalizar_fecha_hora_cita(fecha_hora: str) -> datetime.datetime:
    texto = (fecha_hora or "").strip().replace(" ", "T")
    if len(texto) == 10:
        raise ValueError("Falta la hora")
    if len(texto) == 16:
        texto += ":00"
    return datetime.datetime.fromisoformat(texto)


def _seleccionar_cita_paciente(citas: list[dict], fecha_hora: str = "") -> dict | None:
    if not citas:
        return None
    if not fecha_hora:
        return citas[0]
    try:
        objetivo = _normalizar_fecha_hora_cita(fecha_hora)
    except ValueError:
        return None
    coincidencias = []
    for cita in citas:
        try:
            inicio = _normalizar_fecha_hora_cita(f"{cita['fecha']}T{cita['hora']}")
        except ValueError:
            continue
        if inicio == objetivo:
            coincidencias.append(cita)
    if len(coincidencias) == 1:
        return coincidencias[0]
    if len(coincidencias) > 1:
        return None
    return citas[0]


def listar_citas_futuras_por_telefono(telefono_paciente: str) -> list[dict]:
    """Busca citas futuras del paciente en todos los calendarios por número."""
    cache_key = _normalizar_telefono_digitos(telefono_paciente)
    cached = _citas_cache.get(cache_key)
    if cached and time.time() - cached["ts"] < config.CITAS_CACHE_TTL:
        return cached["citas"]

    citas = []
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
                maxResults=20,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            for event in events_result.get("items", []):
                desc = event.get("description", "")
                desc_digits = re.sub(r"\D", "", desc)
                if target_10_digits not in desc_digits or len(target_10_digits) <= 5:
                    continue

                start_str = event["start"].get("dateTime") or event["start"].get("date")
                if not start_str:
                    continue

                if "T" in start_str:
                    hora_cita = (
                        datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        .astimezone(ZONA)
                        .replace(tzinfo=None)
                    )
                    fecha = hora_cita.strftime("%Y-%m-%d")
                    hora = hora_cita.strftime("%H:%M")
                else:
                    hora_cita = datetime.datetime.strptime(start_str[:10], "%Y-%m-%d")
                    fecha = start_str[:10]
                    hora = "Todo el día"

                diferencia = hora_cita - ahora_naive
                citas.append(
                    {
                        "event_id": event.get("id", ""),
                        "calendar_id": cal_id,
                        "fecha": fecha,
                        "hora": hora,
                        "especialista": _especialista_desde_calendario(cal_id),
                        "servicio": _parsear_servicio_descripcion(desc),
                        "resumen": event.get("summary", ""),
                        "dias_restantes": max(0, diferencia.days),
                        "horas_restantes": max(0, int(diferencia.total_seconds() // 3600)),
                    }
                )
    except Exception as e:
        logger.error("Error listando citas por teléfono: %s", e)

    citas.sort(key=lambda c: (c["fecha"], c["hora"]))
    _citas_cache[cache_key] = {"citas": citas, "ts": time.time()}
    return citas


def consultar_mis_citas(telefono: str):
    """
    Consulta las citas futuras del paciente usando su número de teléfono.
    Busca en todos los calendarios de Inpulso.
    """
    citas = listar_citas_futuras_por_telefono(telefono)
    if not citas:
        return (
            "INSTRUCCIÓN PARA LA IA: No hay citas futuras registradas con este número de teléfono. "
            "Pregunta amablemente si agendó con otro número o si desea agendar una nueva cita."
        )

    resumen = []
    for c in citas:
        resumen.append(
            f"{c['fecha']} a las {c['hora']} con {c['especialista']} "
            f"({c['servicio']}) — en {c['dias_restantes']} día(s)"
        )
    return "CITAS DEL PACIENTE: " + " | ".join(resumen)


def obtener_contexto_perfil_paciente(telefono: str) -> str:
    """Memoria permanente: nombre asociado al número de WhatsApp."""
    nombre = storage.obtener_nombre_paciente(telefono)
    memoria_extra = ""
    try:
        from conversacion import clave_conversacion_whatsapp

        msgs = storage.obtener_mensajes_conversacion(
            clave_conversacion_whatsapp(telefono), limite=4
        )
        if msgs:
            pistas = []
            for m in msgs[-4:]:
                rol = "Paciente" if m["rol"] == "user" else "Alessia"
                pistas.append(f"{rol}: {m['contenido'][:120]}")
            memoria_extra = (
                "[Sistema: ÚLTIMOS MENSAJES — Continúa el hilo con naturalidad, "
                "sin repetir saludos ni presentaciones.]\n"
                + "\n".join(pistas)
                + "\n"
            )
    except Exception:
        pass

    if not nombre:
        return (
            "[Sistema: PERFIL PACIENTE — Sin nombre guardado para este número. "
            "NO pidas nombre para charlar; solo si agendará cita o se inscribirá a taller "
            "pide nombre COMPLETO (nombre y apellidos). Si se presenta casualmente, "
            "usa recordar_nombre_paciente. Mantén tono cálido con emojis.]\n"
            + memoria_extra
        )
    primero = nombre.strip().split()[0]
    completo = "sí" if storage.tiene_nombre_completo(telefono) else "no"
    return (
        f"[Sistema: PERFIL PACIENTE — Memoria permanente por teléfono. "
        f"Nombre guardado: {nombre} (primer nombre: {primero}). "
        f"Nombre completo en archivo: {completo}. "
        f"Salúdalo por '{primero}' con calidez y emojis. PROHIBIDO preguntar cómo se llama para platicar. "
        f"Solo pide nombre y apellidos al agendar cita o inscribir a taller si aún no es completo.]\n"
        + memoria_extra
    )


def recordar_nombre_paciente(telefono: str, nombre: str):
    """Guarda el nombre del paciente asociado a su teléfono (memoria permanente)."""
    storage.guardar_nombre_casual(telefono, nombre)
    primero = storage.primer_nombre(telefono) or nombre.strip().split()[0]
    return (
        f"ÉXITO: Nombre guardado ({primero}). INSTRUCCIÓN PARA LA IA: "
        f"Dirígete a {primero} por su primer nombre. No vuelvas a preguntar su nombre para charlar."
    )


def obtener_contexto_citas_paciente(telefono: str) -> str:
    """
    Contexto automático para inyectar en cada mensaje del paciente.
    Incluye recordatorio proactivo si la cita es dentro de 7 días.
    """
    citas = listar_citas_futuras_por_telefono(telefono)
    if not citas:
        return "[Sistema: Este paciente NO tiene citas futuras con este número.]\n"

    lineas = ["[Sistema: CITAS REGISTRADAS DE ESTE PACIENTE]"]
    for c in citas:
        lineas.append(
            f"- {c['fecha']} {c['hora']} con {c['especialista']} ({c['servicio']})"
        )

    proxima = citas[0]
    cita_clave = f"{proxima['fecha']}_{proxima['hora']}_{proxima['especialista']}"

    if proxima["dias_restantes"] <= 7 and not storage.ya_menciono_cita_proactiva(telefono, cita_clave):
        lineas.append(
            f"[RECORDATORIO PROACTIVO (mencionar UNA sola vez con naturalidad): "
            f"Tiene cita el {proxima['fecha']} a las {proxima['hora']} con {proxima['especialista']}. "
            f"Puedes recordárselo con calidez si encaja en la plática (llegar 10 min antes). "
            f"NO repitas este recordatorio en mensajes siguientes.]"
        )
        storage.marcar_cita_proactiva_mencionada(telefono, cita_clave)

    return "\n".join(lineas) + "\n"


def envolver_mensaje_con_contexto_paciente(telefono: str, contenido):
    """Anteponer contexto de fecha (y citas del paciente si no es staff)."""
    from google.genai import types

    if config.ENABLE_MODO_EQUIPO:
        from modo_equipo import envolver_mensaje_equipo, sesion_equipo_activa

        if sesion_equipo_activa(telefono):
            return envolver_mensaje_equipo(telefono, contenido)

    ctx = obtener_contexto_fecha_actual() + obtener_contexto_perfil_paciente(telefono)
    if config.identificar_terapeuta(telefono):
        ctx += (
            "[Sistema: MODO STAFF — El remitente es terapeuta.\n"
            "- Si pregunta por *sus citas* / *quién tiene* / *pacientes agendados*: "
            "usa ver_mis_citas_agendadas (NO consultar_mi_disponibilidad).\n"
            "- consultar_mi_disponibilidad es SOLO para huecos LIBRES para agendar.\n"
            "- Usa validar_fecha_cita para saber qué fecha es 'el lunes' u otro día.]\n"
        )
    else:
        ctx += obtener_contexto_citas_paciente(telefono)
    pista = _pista_texto_desde_contenido(contenido)
    if config.ENABLE_INPULSO_WEB_LIVE:
        from inpulso_web_live import obtener_contexto_web_en_vivo

        ctx += obtener_contexto_web_en_vivo(pista)
    if config.ENABLE_INPULSO_RAG:
        from inpulso_rag import contexto_rag_para_mensaje

        ctx += contexto_rag_para_mensaje(pista)
    if isinstance(contenido, str):
        return ctx + contenido
    if isinstance(contenido, list):
        return [types.Part(text=ctx)] + contenido
    return contenido


def agendar_cita(
    servicio: str,
    fecha_hora: str,
    nombre_paciente: str,
    especialista: str,
    telefono_paciente: str = "",
):
    """Agenda cita. Para sesiones en línea, servicio debe incluir 'online' (ej. 'Consulta online')."""
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

        especialista_texto = NOMBRES_TERAPEUTAS.get(nombre_clave, especialista.title())
        es_online = _es_servicio_online(servicio)

        descripcion_cita = (
            f"Cita ONLINE de {servicio} con {especialista_texto}. "
            f"Teléfono: {telefono_paciente}"
            if es_online
            else (
                f"Cita de {servicio} con {especialista_texto}. "
                f"Teléfono: {telefono_paciente}"
            )
        )
        event = {
            "summary": nombre_paciente.upper(),
            "description": descripcion_cita,
            "start": {
                "dateTime": fecha_inicio.isoformat(),
                "timeZone": config.ZONA_MEXICO,
            },
            "end": {
                "dateTime": fecha_fin.isoformat(),
                "timeZone": config.ZONA_MEXICO,
            },
        }
        if es_online:
            event["location"] = "Sesión online — Inpulso 43"

        evento_creado = ejecutar_con_reintento(
            lambda: service.events().insert(calendarId=calendar_id, body=event).execute(),
            f"calendar.insert {calendar_id}",
        )
        if not evento_creado.get("id"):
            return "ERROR CRITICO: Google Calendar no devolvió confirmación."

        _invalidar_cache_agenda(calendar_id, fecha_inicio.strftime("%Y-%m-%d"))

        _quitar_de_lista_espera(telefono_paciente)
        _invalidar_cache_citas(telefono_paciente)
        storage.resetear_menciones_proactivas(telefono_paciente)
        if telefono_paciente:
            storage.guardar_nombre_paciente(telefono_paciente, nombre_paciente)
            storage.registrar_primera_cita_si_nueva(
                telefono_paciente, fecha_inicio.strftime("%Y-%m-%d")
            )
            if es_online:
                registrar_pago_cita_online(
                    telefono_paciente,
                    fecha_inicio.strftime("%Y-%m-%d %H:%M"),
                    especialista_texto,
                )

        enlace_calendario = _construir_enlace_google_calendar(
            fecha_inicio, fecha_fin, especialista_texto, servicio, es_online
        )
        bloque = _formatear_confirmacion_cita(
            fecha_inicio, especialista_texto, servicio, es_online=es_online
        )

        confirmacion_enviada = False
        if telefono_paciente:
            from whatsapp import enviar_mensaje_con_boton_url, enviar_mensaje_whatsapp

            confirmacion_enviada = enviar_mensaje_con_boton_url(
                telefono_paciente,
                bloque,
                "Agregar calendario",
                enlace_calendario,
            )
            if not confirmacion_enviada:
                bloque_fallback = bloque.replace(
                    "\n\n📅 Toca el botón de abajo para agregarla a tu calendario 🙌",
                    f"\n\n📅 Agregar a tu calendario:\n{enlace_calendario}",
                )
                confirmacion_enviada = enviar_mensaje_whatsapp(
                    telefono_paciente, bloque_fallback
                )

        if confirmacion_enviada:
            extra_online = (
                " Recuerda con calidez el pago total al confirmar (máx. 24 h antes) "
                "si aún no lo mencionaste."
                if es_online
                else ""
            )
            return (
                f"ÉXITO: Cita guardada correctamente. INSTRUCCIÓN PARA LA IA: "
                f"La confirmación con *botón de calendario* ya fue enviada al paciente "
                f"por WhatsApp.{extra_online} "
                f"Responde solo con 1-2 frases cálidas de seguimiento (emojis bienvenidos). "
                f"PROHIBIDO repetir fecha, hora, terapeuta ni el bloque de confirmación."
            )

        return (
            f"ÉXITO: Cita guardada correctamente. INSTRUCCIÓN PARA LA IA: "
            f"Envía al paciente EXACTAMENTE este bloque de confirmación "
            f"(puedes añadir una frase cálida antes o después, pero conserva el bloque completo):\n\n{bloque}"
        )
    except GoogleCalendarError as e:
        logger.error("Error al agendar cita (calendar): %s", e)
        return (
            "ERROR_CALENDARIO_TEMPORAL: No se guardó la cita aún. INSTRUCCIÓN PARA LA IA: "
            "Vuelve a llamar consultar_agenda y, si el horario sigue libre, reintenta agendar_cita. "
            "Di algo natural como que confirmas la cita en un momento. "
            "NO menciones errores técnicos ni recepción."
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
                    _invalidar_cache_citas(telefono_paciente)
                    storage.resetear_menciones_proactivas(telefono_paciente)
                    if start_str:
                        clave_esp = _especialista_clave_desde_calendario(cal_id)
                        notificar_lista_espera_inmediata(
                            hora_cita.strftime("%Y-%m-%d"), clave_esp
                        )
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


def _especialista_clave_desde_calendario(calendar_id: str) -> str:
    for clave, cal_id in config.DIRECTORIO_CALENDARIOS.items():
        if cal_id == calendar_id:
            return clave
    return ""


def notificar_lista_espera_inmediata(fecha: str, especialista_clave: str):
    """Tras una cancelación, avisa al primer paciente en lista de espera."""
    if not config.ID_HOJA_CALCULO or not especialista_clave:
        return
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Lista_Espera!A:F"
        ).execute()
        rows = result.get("values", [])
        disp = consultar_agenda(fecha, especialista_clave)
        if "Espacios DISPONIBLES" not in disp:
            return
        horarios = disp.split("): ")[1] if "): " in disp else ""
        from whatsapp import enviar_mensaje_whatsapp

        for i, row in enumerate(rows):
            if len(row) < 6 or row[5] != "PENDIENTE":
                continue
            nombre, telefono, esp, fecha_row = row[1], row[2], row[3], row[4]
            if fecha_row != fecha:
                continue
            if especialista_clave.lower() not in esp.lower() and esp.lower() not in especialista_clave.lower():
                continue
            msg = (
                f"✨ ¡Hola {nombre}!\n\nSe acaba de liberar un espacio con "
                f"{esp.title()} el {fecha}. 🎉\n\nHorarios: {horarios}\n\n"
                f"¿Te gustaría agendar? Escríbeme pronto antes de que alguien más lo tome 😊"
            )
            if enviar_mensaje_whatsapp(telefono, msg):
                service.spreadsheets().values().update(
                    spreadsheetId=config.ID_HOJA_CALCULO,
                    range=f"Lista_Espera!F{i+1}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [["NOTIFICADO"]]},
                ).execute()
            break
    except Exception as e:
        logger.warning("Error lista espera inmediata: %s", e)


def bloquear_horario_calendario(
    especialista: str,
    fecha_hora_inicio: str,
    fecha_hora_fin: str,
    motivo: str = "Horario bloqueado",
):
    """Bloquea un rango de horario en el calendario del terapeuta."""
    nombre_clave = _resolver_especialista(especialista)
    if not nombre_clave:
        return "ERROR: Especialista no encontrado."
    try:
        inicio = datetime.datetime.fromisoformat(fecha_hora_inicio.replace(" ", "T"))
        fin = datetime.datetime.fromisoformat(fecha_hora_fin.replace(" ", "T"))
        calendar_id = config.DIRECTORIO_CALENDARIOS[nombre_clave]
        service = get_calendar_service()
        event = {
            "summary": f"BLOQUEADO — {motivo}",
            "description": "Bloqueo creado por Alessia (modo staff)",
            "start": {"dateTime": inicio.isoformat(), "timeZone": config.ZONA_MEXICO},
            "end": {"dateTime": fin.isoformat(), "timeZone": config.ZONA_MEXICO},
        }
        service.events().insert(calendarId=calendar_id, body=event).execute()
        return f"ÉXITO: Horario bloqueado del {inicio} al {fin}."
    except Exception as e:
        logger.error("Error bloqueando horario: %s", e)
        return "ERROR: No se pudo bloquear el horario."


def obtener_mi_codigo_referido(telefono: str):
    """Devuelve el código de referido del paciente para invitar amigos."""
    codigo = storage.obtener_o_crear_codigo_referido(telefono)
    return (
        f"Código de referido: {codigo}. INSTRUCCIÓN PARA LA IA: Explícale que si un amigo "
        f"escribe ese código al registrarse, recibe {config.REFERIDO_DESCUENTO} (aplican políticas "
        f"de la clínica). Comparte con calidez, sin presión."
    )


def registrar_codigo_referido(telefono: str, codigo: str):
    """Registra que un paciente nuevo usó un código de referido."""
    ok = storage.registrar_uso_referido(codigo.strip().upper(), telefono)
    if ok:
        return (
            f"ÉXITO: Referido {codigo} registrado. INSTRUCCIÓN PARA LA IA: Agradece y confirma "
            f"el beneficio de {config.REFERIDO_DESCUENTO} en recepción."
        )
    return "INSTRUCCIÓN PARA LA IA: Código inválido o ya usado. Pide verificar amablemente."


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

        if telefono and nombre:
            storage.guardar_nombre_paciente(telefono, nombre)

        return (
            "INSTRUCCIÓN PARA LA IA: Confírmale al paciente de forma muy alegre, humana "
            "y con emojis que sus datos han sido registrados con éxito. Indícale los "
            "datos bancarios para transferencia y pídele que envíe su comprobante por "
            "aquí para confirmar su inscripción. NO digas que la IA o el sistema lo "
            "confirma automáticamente."
        )
    except Exception as e:
        logger.error("Error registrar taller: %s", e)
        return "INSTRUCCIÓN PARA LA IA: Hubo un fallo al registrar en Sheets."


def obtener_concepto_pago_reciente(telefono: str) -> str:
    """Último taller inscrito o pago de cita asociado al teléfono."""
    concepto = "Servicio Inpulso 43"
    if not config.ID_HOJA_CALCULO:
        return concepto
    target = _normalizar_telefono_digitos(telefono)
    try:
        service = get_sheets_service()
        insc = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Inscripciones!A:F"
        ).execute()
        for row in reversed(insc.get("values", [])):
            if len(row) < 5:
                continue
            if target in re.sub(r"\D", "", row[2]) and len(target) > 5:
                return row[4].strip() or concepto
        pagos = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="PagosCitas!A:G"
        ).execute()
        for row in reversed(pagos.get("values", [])):
            if len(row) < 4:
                continue
            if target in re.sub(r"\D", "", row[1]) and len(target) > 5:
                return (row[3] if len(row) > 3 else "").strip() or "Cita en línea Inpulso 43"
    except Exception as e:
        logger.debug("Concepto recibo no disponible: %s", e)
    return concepto


def _intentar_enviar_recibo_pago(telefono: str, monto: float):
    try:
        from recibos import enviar_recibo_pago

        nombre = (
            storage.obtener_nombre_paciente(telefono)
            or storage.primer_nombre(telefono)
            or "Paciente"
        )
        concepto = obtener_concepto_pago_reciente(telefono)
        enviar_recibo_pago(telefono, nombre, concepto, monto)
    except Exception as e:
        logger.warning("No se pudo enviar recibo a %s: %s", telefono, e)


def confirmar_pago_comprobante(telefono: str, monto_comprobante: float):
    """
    Confirma automáticamente el pago tras validar comprobante y monto.
    Usar SOLO si la imagen muestra transferencia COMPLETADA a cuenta válida de Inpulso
    y el monto coincide con el precio del taller inscrito.
    """
    cuentas = obtener_cuentas_pago_texto()
    ok, detalle = validar_monto_pago(telefono, monto_comprobante)
    if not ok:
        return (
            f"RECHAZADO: {detalle} INSTRUCCIÓN PARA LA IA: Explica amablemente al paciente "
            f"que el monto no coincide o falta inscripción. Cuentas válidas: {cuentas}."
        )

    resultado = actualizar_pago_paciente(telefono, "PAGADO")
    ok_cita, detalle_cita = confirmar_pago_cita_online(telefono, monto_comprobante)
    if "actualizado a PAGADO" in resultado or "Estatus de pago actualizado" in resultado:
        _intentar_enviar_recibo_pago(telefono, monto_comprobante)
        extra = f" {detalle_cita}" if ok_cita else ""
        return (
            f"ÉXITO: Pago confirmado ({detalle}).{extra} INSTRUCCIÓN PARA LA IA: "
            "Felicita al paciente con calidez — su inscripción quedó confirmada. ✨ "
            "El sistema ya envió (o intentó enviar) el recibo gráfico por WhatsApp. "
            "NO menciones validación automática, IA ni revisión del comprobante."
        )
    if ok_cita:
        _intentar_enviar_recibo_pago(telefono, monto_comprobante)
        return (
            f"ÉXITO: {detalle_cita} INSTRUCCIÓN PARA LA IA: "
            "Felicita al paciente — el pago de su cita online quedó confirmado. ✨ "
            "El recibo gráfico se envió por WhatsApp si fue posible."
        )
    return (
        f"{resultado} {detalle} Cuentas válidas: {cuentas}. "
        "INSTRUCCIÓN PARA LA IA: Si no hay registro previo, primero usa registrar_paciente_taller."
    )


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
            spreadsheetId=config.ID_HOJA_CALCULO, range="Inscripciones!A:F"
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


def reagendar_cita_inteligente(telefono_paciente: str):
    """Cancela la próxima cita y ofrece hasta 3 horarios alternativos."""
    from experiencia import reagendar_cita_inteligente as _reagendar

    return _reagendar(telefono_paciente)


def guardar_prep_sesion(
    telefono: str,
    tema: str,
    es_primera_sesion: str = "",
    animo: int = 0,
):
    """Guarda respuestas de prep de sesión (24 h antes) para el terapeuta."""
    from experiencia import guardar_prep_sesion as _guardar

    return _guardar(telefono, tema, es_primera_sesion, animo)


def guardar_nota_ritual_cierre(telefono: str, nota: str):
    """Guarda reflexión privada post-sesión del paciente."""
    from experiencia import guardar_nota_ritual_cierre as _guardar

    return _guardar(telefono, nota)


def registrar_interes_taller(
    telefono: str,
    terapeuta: str,
    taller_nombre: str = "",
):
    """Registra interés para avisar cuando ese terapeuta publique un nuevo taller."""
    nombre = storage.obtener_nombre_paciente(telefono) or ""
    storage.registrar_interes_taller(telefono, terapeuta, taller_nombre, nombre)
    return (
        f"ÉXITO: Interés registrado para talleres de {terapeuta}. "
        f"INSTRUCCIÓN PARA LA IA: Avisa al paciente con calidez y emojis que "
        f"le escribiremos por aquí cuando {terapeuta} publique un nuevo taller "
        f"similar. No prometas fechas exactas."
    )


def _cuentas_clabe_validas() -> set[str]:
    return {
        config.CUENTAS_OFICIALES["BANORTE"]["clabe"],
        config.CUENTAS_OFICIALES["BANAMEX"]["clabe"],
    }


def validar_cuenta_destino(clabe_o_cuenta: str) -> bool:
    """True si la cuenta destino del comprobante es de Inpulso."""
    digitos = re.sub(r"\D", "", clabe_o_cuenta or "")
    if len(digitos) < 10:
        return False
    for valida in _cuentas_clabe_validas():
        if not valida:
            continue
        if valida in digitos or digitos.endswith(valida[-10:]):
            return True
    return False


def _asegurar_hoja(service, titulo: str, encabezados: list[str]) -> bool:
    meta = service.spreadsheets().get(spreadsheetId=config.ID_HOJA_CALCULO).execute()
    tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if titulo in tabs:
        return True
    service.spreadsheets().batchUpdate(
        spreadsheetId=config.ID_HOJA_CALCULO,
        body={"requests": [{"addSheet": {"properties": {"title": titulo}}}]},
    ).execute()
    cols = chr(ord("A") + len(encabezados) - 1)
    service.spreadsheets().values().update(
        spreadsheetId=config.ID_HOJA_CALCULO,
        range=f"{titulo}!A1:{cols}1",
        valueInputOption="USER_ENTERED",
        body={"values": [encabezados]},
    ).execute()
    return True


def registrar_solicitud_facturacion(
    telefono: str,
    razon_social: str,
    rfc: str,
    domicilio_fiscal: str,
    dia_cita: str,
    horario_cita: str,
    metodo_pago: str,
    uso_cfdi: str,
    notas: str = "",
):
    """Registra solicitud de factura CFDI en Google Sheets y avisa a recepción."""
    if not config.ID_HOJA_CALCULO:
        return (
            "INSTRUCCIÓN PARA LA IA: No pude registrar la solicitud por fallo técnico. "
            "Pide al paciente enviar los datos a recepción."
        )
    nombre = storage.obtener_nombre_paciente(telefono) or ""
    try:
        service = get_sheets_service()
        _asegurar_hoja(
            service,
            "Facturacion",
            [
                "Fecha",
                "Teléfono",
                "Nombre",
                "Razón social",
                "RFC",
                "Domicilio fiscal",
                "Día cita",
                "Horario",
                "Método pago",
                "Uso CFDI",
                "Estado",
                "Notas",
            ],
        )
        fecha = datetime.datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")
        service.spreadsheets().values().append(
            spreadsheetId=config.ID_HOJA_CALCULO,
            range="Facturacion!A:L",
            valueInputOption="USER_ENTERED",
            body={
                "values": [[
                    fecha,
                    telefono,
                    nombre,
                    razon_social,
                    rfc.upper(),
                    domicilio_fiscal,
                    dia_cita,
                    horario_cita,
                    metodo_pago,
                    uso_cfdi,
                    "PENDIENTE",
                    notas,
                ]]
            },
        ).execute()
    except Exception as e:
        logger.error("Error registrando facturación: %s", e)
        return "INSTRUCCIÓN PARA LA IA: Fallo al guardar facturación. Pide contactar recepción."

    if config.RECEPCION_WHATSAPP:
        from whatsapp import enviar_mensaje_whatsapp

        aviso = (
            f"🧾 *Solicitud de factura*\n"
            f"Paciente: {nombre or 'Sin nombre'}\n"
            f"Tel: {telefono}\n"
            f"RFC: {rfc.upper()}\n"
            f"Razón social: {razon_social}\n"
            f"Cita: {dia_cita} {horario_cita}\n"
            f"Uso CFDI: {uso_cfdi}\n\n"
            f"Revisa hoja Facturacion en Google Sheets."
        )
        enviar_mensaje_whatsapp(config.RECEPCION_WHATSAPP, aviso)

    return (
        "ÉXITO: Solicitud de factura registrada. INSTRUCCIÓN PARA LA IA: "
        "Confirma al paciente con calidez que recepción procesará su factura. "
        "Recuérdale enviar su CSF si aún no la compartió. Tiempo habitual: 3-5 días hábiles."
    )


def registrar_pago_cita_online(
    telefono: str,
    fecha_cita: str,
    especialista: str,
    monto_esperado: float = 0,
    estatus: str = "PENDIENTE",
):
    """Registra pago de cita online en hoja PagosCitas."""
    if not config.ID_HOJA_CALCULO:
        return False
    try:
        service = get_sheets_service()
        _asegurar_hoja(
            service,
            "PagosCitas",
            ["Fecha registro", "Teléfono", "Nombre", "Fecha cita", "Especialista", "Monto", "Estatus"],
        )
        nombre = storage.obtener_nombre_paciente(telefono) or ""
        fecha = datetime.datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")
        service.spreadsheets().values().append(
            spreadsheetId=config.ID_HOJA_CALCULO,
            range="PagosCitas!A:G",
            valueInputOption="USER_ENTERED",
            body={
                "values": [[fecha, telefono, nombre, fecha_cita, especialista, monto_esperado, estatus]]
            },
        ).execute()
        return True
    except Exception as e:
        logger.error("Error registrando pago cita online: %s", e)
        return False


def confirmar_pago_cita_online(telefono: str, monto: float) -> tuple[bool, str]:
    """Marca PAGADO el pago de cita online más reciente del teléfono."""
    if not config.ID_HOJA_CALCULO:
        return False, "Sin hoja de cálculo"
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="PagosCitas!A:G"
        ).execute()
        rows = result.get("values", [])
        target = _normalizar_telefono_digitos(telefono)
        for i in range(len(rows) - 1, 0, -1):
            row = rows[i]
            if len(row) < 7:
                continue
            row_digits = re.sub(r"\D", "", row[1])
            if target not in row_digits or row[6].upper() != "PENDIENTE":
                continue
            service.spreadsheets().values().update(
                spreadsheetId=config.ID_HOJA_CALCULO,
                range=f"PagosCitas!F{i+1}:G{i+1}",
                valueInputOption="USER_ENTERED",
                body={"values": [[monto, "PAGADO"]]},
            ).execute()
            return True, f"Pago de cita online confirmado (${monto:.0f})."
        return False, "No hay pago de cita online PENDIENTE."
    except Exception as e:
        logger.error("Error confirmando pago cita: %s", e)
        return False, "Error técnico"


def cambiar_servicio_cita(
    telefono_paciente: str,
    nuevo_servicio: str,
    fecha_hora: str = "",
):
    """
    Actualiza el tipo o modalidad de una cita existente sin cambiar día ni hora.
    Usar cuando el paciente pida pasar de individual a pareja, presencial a online, etc.
    """
    citas = listar_citas_futuras_por_telefono(telefono_paciente)
    if not citas:
        return (
            "INSTRUCCIÓN PARA LA IA: No hay cita futura para actualizar. "
            "Usa agendar_cita si necesita una cita nueva."
        )

    cita = _seleccionar_cita_paciente(citas, fecha_hora)
    if not cita:
        return (
            "INSTRUCCIÓN PARA LA IA: Hay varias citas con ese horario. "
            "Pregunta cuál desea cambiar o usa consultar_mis_citas."
        )

    event_id = cita.get("event_id")
    calendar_id = cita.get("calendar_id")
    if not event_id or not calendar_id:
        return "ERROR: No se pudo localizar la cita en el calendario."

    try:
        service = get_calendar_service()
        evento = ejecutar_con_reintento(
            lambda: service.events()
            .get(calendarId=calendar_id, eventId=event_id)
            .execute(),
            f"calendar.get {calendar_id}",
        )

        especialista_texto = cita["especialista"]
        es_online = _es_servicio_online(nuevo_servicio)
        descripcion_cita = (
            f"Cita ONLINE de {nuevo_servicio} con {especialista_texto}. "
            f"Teléfono: {telefono_paciente}"
            if es_online
            else (
                f"Cita de {nuevo_servicio} con {especialista_texto}. "
                f"Teléfono: {telefono_paciente}"
            )
        )
        evento["description"] = descripcion_cita
        if es_online:
            evento["location"] = "Sesión online — Inpulso 43"
        else:
            evento.pop("location", None)

        ejecutar_con_reintento(
            lambda: service.events()
            .patch(calendarId=calendar_id, eventId=event_id, body=evento)
            .execute(),
            f"calendar.patch {calendar_id}",
        )

        _invalidar_cache_agenda(calendar_id, cita["fecha"])
        _invalidar_cache_citas(telefono_paciente)

        fecha_inicio = _normalizar_fecha_hora_cita(f"{cita['fecha']}T{cita['hora']}")
        bloque = _formatear_confirmacion_cita(
            fecha_inicio, especialista_texto, nuevo_servicio, es_online=es_online
        )
        servicio_anterior = cita.get("servicio", "consulta")
        return (
            f"ÉXITO: Cita actualizada de '{servicio_anterior}' a '{nuevo_servicio}' "
            f"el {cita['fecha']} a las {cita['hora']} con {especialista_texto}. "
            f"INSTRUCCIÓN PARA LA IA: El cambio ya quedó guardado en la agenda. "
            f"Confirma con calidez el nuevo tipo de cita (mismo día y hora). "
            f"Puedes usar este bloque si hace falta:\n\n{bloque}"
        )
    except GoogleCalendarError as e:
        logger.error("Error al cambiar servicio de cita: %s", e)
        return (
            "ERROR_CALENDARIO_TEMPORAL: No se pudo actualizar la cita aún. "
            "INSTRUCCIÓN PARA LA IA: Reintenta cambiar_servicio_cita en un momento."
        )
    except Exception as e:
        logger.error("Error al cambiar servicio de cita: %s", e)
        return "ERROR: No se pudo actualizar el tipo de cita."


def reagendar_cita_atomica(
    telefono_paciente: str,
    nueva_fecha_hora: str,
    nombre_paciente: str,
    especialista: str,
    servicio: str,
):
    """Agenda la nueva cita y cancela la anterior en un solo paso."""
    citas = listar_citas_futuras_por_telefono(telefono_paciente)
    if not citas:
        return (
            "INSTRUCCIÓN PARA LA IA: No hay cita previa. Usa agendar_cita directamente."
        )

    vieja = _seleccionar_cita_paciente(citas, nueva_fecha_hora) or citas[0]
    try:
        hora_vieja = _normalizar_fecha_hora_cita(f"{vieja['fecha']}T{vieja['hora']}")
        hora_nueva = _normalizar_fecha_hora_cita(nueva_fecha_hora)
        if hora_vieja == hora_nueva:
            return cambiar_servicio_cita(telefono_paciente, servicio, nueva_fecha_hora)
    except ValueError:
        pass

    resultado_agendar = agendar_cita(
        servicio, nueva_fecha_hora, nombre_paciente, especialista, telefono_paciente
    )
    if "ERROR" in resultado_agendar.upper():
        return resultado_agendar
    vieja = citas[0]
    resultado_cancelar = _cancelar_cita_especifica(telefono_paciente, vieja)
    storage.limpiar_reagendar_pendiente(telefono_paciente)
    return (
        f"{resultado_agendar} {resultado_cancelar} "
        f"INSTRUCCIÓN PARA LA IA: Confirma el reagendado con calidez. "
        f"Nueva cita: {nueva_fecha_hora}."
    )


def _cancelar_cita_especifica(telefono_paciente: str, cita: dict) -> str:
    """Cancela una cita específica por event_id si está disponible."""
    event_id = cita.get("event_id")
    if not event_id:
        return cancelar_cita_paciente(telefono_paciente)
    try:
        service = get_calendar_service()
        for cal_id in config.DIRECTORIO_CALENDARIOS.values():
            try:
                service.events().delete(calendarId=cal_id, eventId=event_id).execute()
                _invalidar_cache_citas(telefono_paciente)
                storage.resetear_menciones_proactivas(telefono_paciente)
                return "La cita anterior fue cancelada."
            except Exception:
                continue
    except Exception as e:
        logger.error("Error cancelando cita específica: %s", e)
    return cancelar_cita_paciente(telefono_paciente)


def eliminar_datos_arco(telefono: str) -> str:
    """
    Borrado ARCO: SQLite local + citas futuras en Calendar + anonimización en Sheets.
    """
    storage.eliminar_datos_paciente(telefono)
    citas_borradas = 0
    try:
        service = get_calendar_service()
        target = _normalizar_telefono_digitos(telefono)
        hoy_utc = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        for cal_id in config.DIRECTORIO_CALENDARIOS.values():
            events = service.events().list(
                calendarId=cal_id,
                timeMin=hoy_utc,
                maxResults=50,
                singleEvents=True,
            ).execute()
            for event in events.get("items", []):
                desc_digits = re.sub(r"\D", "", event.get("description", ""))
                if target in desc_digits and len(target) > 5:
                    service.events().delete(calendarId=cal_id, eventId=event["id"]).execute()
                    citas_borradas += 1
    except Exception as e:
        logger.error("ARCO calendar: %s", e)

    filas_anon = 0
    if config.ID_HOJA_CALCULO:
        try:
            filas_anon = _anonimizar_filas_sheets_por_telefono(telefono)
        except Exception as e:
            logger.error("ARCO sheets: %s", e)

    return (
        f"ÉXITO ARCO: Datos locales eliminados. "
        f"Citas futuras canceladas en calendario: {citas_borradas}. "
        f"Filas anonimizadas en Sheets: {filas_anon}. "
        f"INSTRUCCIÓN PARA LA IA: Confirma al paciente que sus datos fueron eliminados "
        f"de nuestros sistemas automatizados. Si necesita confirmación escrita, "
        f"puede contactar recepción."
    )


def _anonimizar_filas_sheets_por_telefono(telefono: str) -> int:
    """Anonimiza filas con el teléfono en Inscripciones, Lista_Espera, Escalaciones, Facturacion."""
    service = get_sheets_service()
    target = _normalizar_telefono_digitos(telefono)
    anon = "ELIMINADO-ARCO"
    total = 0
    hojas = [
        ("Inscripciones", "C", 2),
        ("Lista_Espera", "C", 2),
        ("Escalaciones", "B", 1),
        ("Facturacion", "B", 2),
        ("PagosCitas", "B", 2),
    ]
    for hoja, col_tel, col_nombre in hojas:
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=config.ID_HOJA_CALCULO, range=f"{hoja}!A:Z"
            ).execute()
            rows = result.get("values", [])
            for i, row in enumerate(rows):
                if i == 0:
                    continue
                idx_tel = ord(col_tel) - ord("A")
                if len(row) <= idx_tel:
                    continue
                if target not in re.sub(r"\D", "", row[idx_tel]):
                    continue
                row[idx_tel] = anon
                if len(row) > col_nombre:
                    row[col_nombre] = anon
                service.spreadsheets().values().update(
                    spreadsheetId=config.ID_HOJA_CALCULO,
                    range=f"{hoja}!A{i+1}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [row]},
                ).execute()
                total += 1
        except Exception as e:
            logger.debug("Anonimizar %s: %s", hoja, e)
    return total


def renotificar_escalaciones_pendientes():
    """Re-avisa a recepción escalaciones PENDIENTE con más de N minutos."""
    if not config.ID_HOJA_CALCULO or not config.RECEPCION_WHATSAPP:
        return 0
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Escalaciones!A:F"
        ).execute()
        rows = result.get("values", [])
        ahora = datetime.datetime.now(ZONA)
        reavisos = 0
        from whatsapp import enviar_mensaje_whatsapp

        for i, row in enumerate(rows):
            if i == 0 or len(row) < 5:
                continue
            if row[4].upper() != "PENDIENTE":
                continue
            notas = row[5] if len(row) > 5 else ""
            if "REAVISO" in notas.upper():
                continue
            try:
                fecha = datetime.datetime.strptime(row[0][:19], "%Y-%m-%d %H:%M:%S")
                fecha = ZONA.localize(fecha)
            except ValueError:
                continue
            if (ahora - fecha).total_seconds() < config.ESCALACION_REAVISO_MINUTOS * 60:
                continue
            aviso = (
                f"⏰ *Re-aviso escalación pendiente*\n"
                f"Tel: {row[1]}\n"
                f"Nombre: {row[2]}\n"
                f"Motivo: {row[3]}\n"
                f"Desde: {row[0]}\n\n"
                f"Sin atender tras {config.ESCALACION_REAVISO_MINUTOS} min."
            )
            if enviar_mensaje_whatsapp(config.RECEPCION_WHATSAPP, aviso):
                service.spreadsheets().values().update(
                    spreadsheetId=config.ID_HOJA_CALCULO,
                    range=f"Escalaciones!F{i+1}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[f"REAVISO {ahora.strftime('%H:%M')}"]]},
                ).execute()
                reavisos += 1
        return reavisos
    except Exception as e:
        logger.error("Error renotificando escalaciones: %s", e)
        return 0

