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
from google_client import get_calendar_service, get_sheets_service

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


def _formatear_fecha_español(fecha: datetime.datetime) -> str:
    dia = DIAS_ES[fecha.weekday()]
    mes = MESES_ES[fecha.month - 1]
    return f"{dia.capitalize()} {fecha.day} de {mes} de {fecha.year}"


def _formatear_confirmacion_cita(
    fecha_inicio: datetime.datetime,
    especialista_texto: str,
    servicio: str,
    enlace_corto: str,
) -> str:
    hora = fecha_inicio.strftime("%I:%M %p").lstrip("0").replace("AM", "a.m.").replace("PM", "p.m.")
    fecha_txt = _formatear_fecha_español(fecha_inicio)
    return (
        f"✅ *Cita confirmada*\n"
        f"📅 {fecha_txt}, {hora}\n"
        f"👩‍⚕️ {especialista_texto}\n"
        f"🩺 {servicio}\n"
        f"📍 {config.CLINICA_DIRECCION}\n"
        f"🗺️ {config.CLINICA_MAPS_URL}\n"
        f"💡 Llega 10 minutos antes\n\n"
        f"Agrega a tu calendario: {enlace_corto}"
    )


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
    """Registra escalación en Google Sheets y opcionalmente avisa a recepción por WhatsApp."""
    if not config.ID_HOJA_CALCULO:
        logger.warning("Escalación sin ID_HOJA_CALCULO: %s", telefono)
        return False

    nombre = storage.obtener_nombre_paciente(telefono) or ""

    try:
        service = get_sheets_service()
        _asegurar_hoja_escalaciones(service)
        fecha = datetime.datetime.now(ZONA).strftime("%Y-%m-%d %H:%M:%S")
        service.spreadsheets().values().append(
            spreadsheetId=config.ID_HOJA_CALCULO,
            range="Escalaciones!A:F",
            valueInputOption="USER_ENTERED",
            body={"values": [[fecha, telefono, nombre, motivo, "PENDIENTE", ""]]},
        ).execute()
        logger.info("Escalación registrada: %s (%s)", telefono, nombre or "sin nombre")
    except Exception as e:
        logger.error("Error registrando escalación: %s", e)
        return False

    if config.RECEPCION_WHATSAPP:
        from whatsapp import enviar_mensaje_whatsapp

        aviso = (
            f"🙋 *Escalación humana*\n"
            f"Tel: {telefono}\n"
            f"Nombre: {nombre or 'No registrado'}\n"
            f"Motivo: {motivo}\n\n"
            f"Revisa la hoja Escalaciones en Google Sheets."
        )
        enviar_mensaje_whatsapp(config.RECEPCION_WHATSAPP, aviso)

    return True


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

    ahora = datetime.datetime.now(ZONA).replace(tzinfo=None)
    if slot_inicio < ahora.replace(minute=0, second=0, microsecond=0):
        return False

    slot_fin = slot_inicio + datetime.timedelta(hours=1)
    for o_start, o_end in ocupados:
        if max(slot_inicio, o_start) < min(slot_fin, o_end):
            return False
    return True


def consultar_precios_y_servicios(especialista: str = "todos"):
    """Consulta precios: primero Google Sheets (Drive), luego precios.json local."""
    from catalogo import _leer_filas_catalogo

    if _leer_filas_catalogo():
        return consultar_catalogo_drive(especialista)

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
    events = _obtener_eventos_dia(calendar_id, fecha)
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
    "juan": "Juan",
    "sara": "Sara Rosales",
    "patricia": "Patricia",
    "ivan": "Iván",
    "nutricion": "Nutricionista",
    "mentoras": "Mentoras",
    "talleres": "Talleres",
}


def _especialista_desde_calendario(calendar_id: str) -> str:
    for clave, cal_id in config.DIRECTORIO_CALENDARIOS.items():
        if cal_id == calendar_id:
            return NOMBRES_TERAPEUTAS.get(clave, clave.title())
    return "Especialista"


def _parsear_servicio_descripcion(descripcion: str) -> str:
    if descripcion.startswith("Cita de "):
        parte = descripcion.split(" con ", 1)[0]
        return parte.replace("Cita de ", "").strip()
    return "Consulta"


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
    """Anteponer contexto de fecha y citas al mensaje que recibe la IA."""
    from google.genai import types

    ctx = obtener_contexto_fecha_actual() + obtener_contexto_citas_paciente(telefono)
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
        _invalidar_cache_citas(telefono_paciente)
        storage.resetear_menciones_proactivas(telefono_paciente)
        if telefono_paciente:
            storage.guardar_nombre_paciente(telefono_paciente, nombre_paciente)

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

        bloque = _formatear_confirmacion_cita(
            fecha_inicio, especialista_texto, servicio, enlace_corto
        )
        return (
            f"ÉXITO: Cita guardada correctamente. INSTRUCCIÓN PARA LA IA: "
            f"Envía al paciente EXACTAMENTE este bloque de confirmación (puedes añadir "
            f"una frase cálida antes o después, pero conserva el bloque completo):\n\n{bloque}"
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
    if "actualizado a PAGADO" in resultado or "Estatus de pago actualizado" in resultado:
        return (
            f"ÉXITO: Pago confirmado ({detalle}). INSTRUCCIÓN PARA LA IA: "
            "Felicita al paciente con calidez — su inscripción quedó confirmada. ✨ "
            "NO menciones validación automática, IA ni revisión del comprobante."
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
