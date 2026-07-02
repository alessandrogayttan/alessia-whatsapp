import datetime
import logging
import re

import pytz
import requests

import config
import storage
from bienestar import frase_del_dia, obtener_clima_zapopan, trivia_de_la_semana
from dashboard import actualizar_dashboard
from google_client import get_calendar_service, get_sheets_service
from tools import consultar_agenda, _especialista_desde_calendario
from whatsapp import enviar_mensaje_whatsapp, enviar_recordatorio

logger = logging.getLogger(__name__)
ZONA = pytz.timezone(config.ZONA_MEXICO)


def limpiar_inscripciones_pendientes_background():
    if not config.ID_HOJA_CALCULO:
        return
    try:
        service = get_sheets_service()
        sheet_metadata = service.spreadsheets().get(
            spreadsheetId=config.ID_HOJA_CALCULO
        ).execute()
        sheet_id_inscripciones = None
        for s in sheet_metadata.get("sheets", []):
            if s.get("properties", {}).get("title") == "Inscripciones":
                sheet_id_inscripciones = s.get("properties", {}).get("sheetId")
                break
        if sheet_id_inscripciones is None:
            return

        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Inscripciones!A:F"
        ).execute()
        rows = result.get("values", [])
        ahora = datetime.datetime.now(ZONA)

        for i in range(len(rows) - 1, 0, -1):
            row = rows[i]
            if len(row) >= 6 and row[5] == "PENDIENTE":
                try:
                    fecha_reg = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                    fecha_reg = ZONA.localize(fecha_reg)
                    if ahora - fecha_reg > datetime.timedelta(hours=24):
                        body = {
                            "requests": [
                                {
                                    "deleteDimension": {
                                        "range": {
                                            "sheetId": sheet_id_inscripciones,
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
                        logger.info("Inscripción eliminada por falta de pago: %s", row[1])
                except ValueError:
                    continue
    except Exception as e:
        logger.error("Error limpieza inscripciones: %s", e)


def _enviar_recordatorio_24h(telefono: str, hora_cita: datetime.datetime, event_id: str):
    from experiencia import mensaje_recordatorio_24h

    if storage.recordatorio_ya_enviado(event_id, "24h"):
        return
    hora_txt = hora_cita.strftime("%H:%M")
    nombre = (
        storage.primer_nombre(telefono)
        or storage.obtener_nombre_paciente(telefono)
        or "hola"
    )
    msg = mensaje_recordatorio_24h(hora_cita)
    if enviar_recordatorio(
        telefono,
        msg,
        config.WHATSAPP_TEMPLATE_24H,
        [nombre, hora_txt],
    ):
        storage.marcar_recordatorio_enviado(event_id, "24h")
        storage.marcar_prep_pendiente(telefono, event_id)


def _enviar_recordatorio_2h(telefono: str, hora_cita: datetime.datetime, event_id: str):
    if storage.recordatorio_ya_enviado(event_id, "2h"):
        return

    ubicacion = storage.obtener_ubicacion(telefono)
    if ubicacion and config.API_KEY_MAPS:
        try:
            url = (
                "https://maps.googleapis.com/maps/api/distancematrix/json"
                f"?origins={ubicacion}"
                "&destinations=Av.+Hidalgo+533,Zapopan"
                "&departure_time=now"
                f"&key={config.API_KEY_MAPS}"
            )
            res = requests.get(url, timeout=15).json()
            if res.get("status") == "OK":
                elemento = res["rows"][0]["elements"][0]
                duracion_normal = elemento["duration"]["value"] / 60
                duracion_trafico = (
                    elemento.get("duration_in_traffic", elemento["duration"])["value"] / 60
                )
                if duracion_trafico > duracion_normal + 10:
                    msg = (
                        f"🚗 *Alerta de Tráfico*\n¡Hola! Tu cita es en 2 horas ({hora_cita.strftime('%H:%M')}). "
                        f"Detecté tráfico en tu ruta (aprox {int(duracion_trafico)} min).\n\n"
                        f"📍 {config.CLINICA_DIRECCION}\n"
                        f"🗺️ {config.CLINICA_MAPS_URL}\n\n"
                        f"¡Te sugiero salir con anticipación! ✨"
                    )
                else:
                    msg = (
                        f"🚗 *Recordatorio Inpulso*\n¡Hola! Tu cita es en 2 horas ({hora_cita.strftime('%H:%M')}). "
                        f"El tráfico está fluido ({int(duracion_trafico)} min).\n\n"
                        f"📍 {config.CLINICA_DIRECCION}\n"
                        f"🗺️ {config.CLINICA_MAPS_URL}\n\n"
                        f"¡Te esperamos! 😊"
                    )
                if enviar_recordatorio(
                    telefono,
                    msg,
                    config.WHATSAPP_TEMPLATE_2H,
                    [
                        storage.primer_nombre(telefono)
                        or storage.obtener_nombre_paciente(telefono)
                        or "hola",
                        hora_cita.strftime("%H:%M"),
                    ],
                ):
                    storage.marcar_recordatorio_enviado(event_id, "2h")
                return
        except requests.RequestException as e:
            logger.warning("Error Maps en recordatorio: %s", e)

    clima = obtener_clima_zapopan()
    clima_txt = f"\n\n{clima}" if clima else ""
    msg = (
        f"🚗 *Recordatorio Inpulso*\n¡Hola! Tu cita es en aprox 2 horas ({hora_cita.strftime('%H:%M')}).\n\n"
        f"📍 {config.CLINICA_DIRECCION}\n"
        f"🗺️ {config.CLINICA_MAPS_URL}\n\n"
        f"Contempla el estacionamiento (sujeto a un cajón disponible). ¡Te esperamos! ✨"
        f"{clima_txt}"
    )
    if enviar_recordatorio(
        telefono,
        msg,
        config.WHATSAPP_TEMPLATE_2H,
        [
            storage.primer_nombre(telefono)
            or storage.obtener_nombre_paciente(telefono)
            or "hola",
            hora_cita.strftime("%H:%M"),
        ],
    ):
        storage.marcar_recordatorio_enviado(event_id, "2h")


def alertas_citas_background():
    ahora_aware = datetime.datetime.now(ZONA)
    ahora_naive = ahora_aware.replace(tzinfo=None)
    try:
        service = get_calendar_service()
        time_min = ahora_aware.isoformat()
        time_max = (ahora_aware + datetime.timedelta(hours=25)).isoformat()

        for cal_id in config.DIRECTORIO_CALENDARIOS.values():
            events_result = service.events().list(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            for event in events_result.get("items", []):
                start_str = event["start"].get("dateTime")
                if not start_str:
                    continue

                event_id = event.get("id", "")
                hora_cita = (
                    datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    .astimezone(ZONA)
                    .replace(tzinfo=None)
                )
                diferencia = hora_cita - ahora_naive

                desc = event.get("description", "")
                phone_match = re.search(r"Teléfono:\s*(\+?\d+)", desc)
                if not phone_match:
                    continue
                telefono = phone_match.group(1)

                if datetime.timedelta(minutes=1425) <= diferencia <= datetime.timedelta(minutes=1440):
                    _enviar_recordatorio_24h(telefono, hora_cita, event_id)
                elif datetime.timedelta(minutes=110) <= diferencia <= datetime.timedelta(minutes=125):
                    _enviar_recordatorio_2h(telefono, hora_cita, event_id)
                elif datetime.timedelta(minutes=25) <= diferencia <= datetime.timedelta(minutes=35):
                    _enviar_resumen_terapeuta(event, telefono, hora_cita, cal_id, event_id)
                    _enviar_eta_salida(telefono, hora_cita, event_id)
                elif datetime.timedelta(minutes=4) <= diferencia <= datetime.timedelta(minutes=6):
                    _enviar_link_online(event, telefono, hora_cita, cal_id, event_id)
    except Exception as e:
        logger.error("Error alertas background: %s", e)


def _enviar_resumen_terapeuta(event, telefono: str, hora_cita, cal_id: str, event_id: str):
    if storage.recordatorio_ya_enviado(event_id, "pre30m"):
        return
    from experiencia import texto_prep_para_terapeuta
    from tools import _resolver_whatsapp_terapeuta

    esp = _especialista_desde_calendario(cal_id)
    info = _resolver_whatsapp_terapeuta(esp)
    if not info:
        return
    display, whatsapp = info
    nombre = storage.obtener_nombre_paciente(telefono) or event.get("summary", "Paciente")
    animo = storage.obtener_ultimo_animo(telefono)
    animo_txt = f"\nÚltimo check-in emocional: {animo}/10" if animo else ""
    prep_txt = texto_prep_para_terapeuta(telefono)
    prep_bloque = f"\n\n📝 Prep del paciente:\n{prep_txt}" if prep_txt else ""
    citas_prev = storage.citas_completadas(telefono)
    tipo = "Primera cita" if citas_prev == 0 else f"Cita #{citas_prev + 1}"
    msg = (
        f"📋 *Resumen pre-sesión (30 min)*\n"
        f"Paciente: {nombre}\n"
        f"Tel: {telefono}\n"
        f"Hora: {hora_cita.strftime('%H:%M')}\n"
        f"Tipo: {tipo}{animo_txt}{prep_bloque}\n"
        f"Servicio: {event.get('description', '')[:120]}"
    )
    if enviar_mensaje_whatsapp(whatsapp, msg):
        storage.marcar_recordatorio_enviado(event_id, "pre30m")


def _enviar_eta_salida(telefono: str, hora_cita: datetime.datetime, event_id: str):
    """Tier 4.14: sugiere salir en X minutos según ubicación y tráfico."""
    if storage.recordatorio_ya_enviado(event_id, "eta30m"):
        return
    from experiencia import calcular_minutos_ruta

    minutos = calcular_minutos_ruta(telefono)
    if not minutos:
        return
    salir_en = max(minutos - 25, 5)
    msg = (
        f"🚗 *Hora de salir*\n\n"
        f"Tu cita es a las {hora_cita.strftime('%H:%M')}. "
        f"Con el tráfico actual, te sugiero salir en unos *{salir_en} minutos* "
        f"(ruta ~{minutos} min).\n\n"
        f"📍 {config.CLINICA_DIRECCION}\n"
        f"🗺️ {config.CLINICA_MAPS_URL}"
    )
    if enviar_mensaje_whatsapp(telefono, msg):
        storage.marcar_recordatorio_enviado(event_id, "eta30m")


def _enviar_link_online(event, telefono: str, hora_cita, cal_id: str, event_id: str):
    """Envía link de videollamada 5 min antes si la cita es online y hay link configurado."""
    if storage.recordatorio_ya_enviado(event_id, "online5m"):
        return
    from experiencia import es_cita_online, link_sesion_online

    if not es_cita_online(event):
        return
    esp = _especialista_desde_calendario(cal_id)
    nombre_esp = esp.title() if esp else "Tu terapeuta"
    link = link_sesion_online(esp)
    if link:
        msg = (
            f"💻 *Tu sesión online empieza pronto*\n\n"
            f"Cita: {hora_cita.strftime('%H:%M')} con {nombre_esp}\n"
            f"🔗 Conéctate aquí:\n{link}\n\n"
            f"Lugar tranquilo, buena conexión y audífonos 🎧"
        )
    else:
        msg = (
            f"💻 *Tu sesión online es hoy*\n\n"
            f"Tu cita es a las {hora_cita.strftime('%H:%M')}.\n"
            f"*{nombre_esp}* te contactará por aquí con el link de Zoom para conectarte ✨\n\n"
            f"Lugar tranquilo, buena conexión y audífonos si puedes 🎧"
        )
    if enviar_mensaje_whatsapp(telefono, msg):
        storage.marcar_recordatorio_enviado(event_id, "online5m")


def seguimiento_post_cita_background():
    """Seguimiento 48 h después de la cita + encuesta NPS tras 3.ª cita."""
    ahora_naive = datetime.datetime.now(ZONA).replace(tzinfo=None)
    try:
        service = get_calendar_service()
        time_min = (ahora_naive - datetime.timedelta(hours=50)).isoformat()
        time_max = (ahora_naive - datetime.timedelta(hours=46)).isoformat()
        for cal_id in config.DIRECTORIO_CALENDARIOS.values():
            events = service.events().list(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
            ).execute()
            for event in events.get("items", []):
                start_str = event["start"].get("dateTime")
                if not start_str:
                    continue
                event_id = event.get("id", "")
                if storage.recordatorio_ya_enviado(event_id, "post48h"):
                    continue
                desc = event.get("description", "")
                phone_match = re.search(r"Teléfono:\s*(\+?\d+)", desc)
                if not phone_match:
                    continue
                telefono = phone_match.group(1)
                nombre = storage.obtener_nombre_paciente(telefono) or storage.primer_nombre(telefono)
                saludo = f"Hola {nombre.split()[0]}" if nombre else "Hola"
                msg = (
                    f"💙 *Seguimiento Inpulso*\n\n"
                    f"{saludo}, hace un par de días tuviste sesión con nosotros. "
                    "¿Cómo te has sentido desde entonces?\n\n"
                    "🌿 *Ritual de cierre* (opcional y privado): "
                    "Si quieres, escribe en un mensaje qué te llevas de esa sesión "
                    "— es solo para ti, no se comparte con tu terapeuta."
                )
                if enviar_mensaje_whatsapp(telefono, msg):
                    storage.marcar_recordatorio_enviado(event_id, "post48h")
                    storage.marcar_ritual_pendiente(telefono, event_id)
                    total = storage.incrementar_citas_completadas(telefono)
                    if total >= 3 and not storage.nps_ya_enviado(telefono):
                        nps = (
                            "⭐ *Tu opinión nos importa*\n\n"
                            "Del 1 al 10, ¿qué tan probable es que recomiendes Inpulso 43 "
                            "a un amigo o familiar?\n\n"
                            "Responde solo con un número (ej. 9)."
                        )
                        enviar_mensaje_whatsapp(telefono, nps)
                        storage.marcar_nps_enviado(telefono)
                        storage.marcar_nps_pendiente(telefono, event_id)
    except Exception as e:
        logger.error("Error seguimiento post-cita: %s", e)


def frase_del_dia_background():
    """Envía frase del día a pacientes que activaron la función (8:00 am)."""
    ahora = datetime.datetime.now(ZONA)
    if ahora.hour != 8 or ahora.minute > 14:
        return
    clave = f"frase_{ahora.strftime('%Y-%m-%d')}"
    if storage.recordatorio_ya_enviado(clave, "global"):
        return
    frase = frase_del_dia()
    enviados = 0
    for telefono in storage.pacientes_frase_dia_activa():
        msg = f"☀️ *Frase del día — Inpulso 43*\n\n{frase}"
        if enviar_mensaje_whatsapp(telefono, msg):
            enviados += 1
    if enviados:
        storage.marcar_recordatorio_enviado(clave, "global")
        logger.info("Frases del día enviadas: %s", enviados)


def trivia_semanal_background():
    """Trivia de bienestar los miércoles (~10 am), una vez por semana por paciente."""
    ahora = datetime.datetime.now(ZONA)
    if ahora.weekday() != 2 or ahora.hour != 10 or ahora.minute > 14:
        return
    semana = ahora.isocalendar()[1]
    trivia = trivia_de_la_semana()
    for telefono in storage.telefonos_pacientes_con_nombre():
        if storage.trivia_enviada_esta_semana(telefono, semana):
            continue
        msg = (
            f"🧠 *Trivia bienestar*\n\n{trivia['pregunta']}\n\n"
            f"💡 {trivia['dato']}"
        )
        if enviar_mensaje_whatsapp(telefono, msg):
            storage.marcar_trivia_enviada(telefono, semana)


def reporte_semanal_background():
    """Reporte los lunes 8:00 am a Sara (o WHATSAPP_SARA)."""
    ahora = datetime.datetime.now(ZONA)
    if ahora.weekday() != 0 or ahora.hour != 8 or ahora.minute > 14:
        return
    clave = f"reporte_{ahora.strftime('%Y-%W')}"
    if storage.recordatorio_ya_enviado(clave, "global"):
        return
    destino = config.TERAPEUTAS_WHATSAPP.get("sara")
    if not destino:
        return
    actualizar_dashboard()
    stats = storage.estadisticas_globales()
    msg = (
        f"📊 *Reporte semanal Inpulso 43*\n\n"
        f"Pacientes registrados: {stats.get('pacientes', 0)}\n"
        f"Referidos activados: {stats.get('referidos', 0)}\n"
        f"Check-ins emocionales (mes): {stats.get('checkins_mes', 0)}\n\n"
        f"Revisa la pestaña *Dashboard* en Google Sheets para más detalle."
    )
    if enviar_mensaje_whatsapp(destino, msg):
        storage.marcar_recordatorio_enviado(clave, "global")


def dashboard_background():
    actualizar_dashboard()


def experiencia_diaria_background():
    """Aniversarios, bienvenida talleres y recordatorios de tareas terapéuticas."""
    from experiencia import (
        procesar_aniversarios,
        procesar_bienvenida_talleres,
        procesar_recordatorios_tareas,
    )

    ahora = datetime.datetime.now(ZONA)
    if ahora.hour == 9 and ahora.minute <= 14:
        procesar_recordatorios_tareas()
    if ahora.hour == 10 and ahora.minute <= 14:
        procesar_aniversarios()
        procesar_bienvenida_talleres()


def detectar_nuevos_talleres_background():
    """Notifica interesados cuando aparece un taller nuevo en el catálogo."""
    from experiencia import procesar_nuevos_talleres_catalogo

    try:
        procesar_nuevos_talleres_catalogo()
    except Exception as e:
        logger.error("Error detectando nuevos talleres: %s", e)


def verificar_lista_espera_background():
    if not config.ID_HOJA_CALCULO:
        return
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Lista_Espera!A:F"
        ).execute()
        rows = result.get("values", [])

        for i, row in enumerate(rows):
            if len(row) >= 6 and row[5] == "PENDIENTE":
                nombre, telefono, especialista, fecha = row[1], row[2], row[3], row[4]
                disp = consultar_agenda(fecha, especialista)
                if "Espacios DISPONIBLES" in disp:
                    horarios_texto = disp.split("): ")[1] if "): " in disp else disp
                    msg = (
                        f"✨ ¡Hola {nombre}!\n\nTe escribo de Inpulso 43 porque se acaba de "
                        f"liberar un espacio con {especialista.title()} para el {fecha}. 🎉\n\n"
                        f"Los horarios que se abrieron son: {horarios_texto}\n\n"
                        f"¿Te gustaría aprovechar y agendar? Avísame pronto antes de que "
                        f"alguien más lo tome. 😊"
                    )
                    if enviar_mensaje_whatsapp(telefono, msg):
                        service.spreadsheets().values().update(
                            spreadsheetId=config.ID_HOJA_CALCULO,
                            range=f"Lista_Espera!F{i+1}",
                            valueInputOption="USER_ENTERED",
                            body={"values": [["NOTIFICADO"]]},
                        ).execute()
    except Exception as e:
        logger.error("Error lista de espera: %s", e)


def calendario_keepalive_background():
    """Mantiene viva la conexión con Google Calendar y recupera tras fallos transitorios."""
    import time

    from google_client import reset_google_clients, verificar_credenciales_google
    from tools import verificar_acceso_calendarios

    try:
        verificar_credenciales_google()
        fallos = verificar_acceso_calendarios(rapido=False)
        if not fallos:
            return
        logger.warning("Keepalive calendario: fallos detectados %s — reintentando", fallos)
        reset_google_clients()
        time.sleep(3)
        verificar_credenciales_google()
        recuperados = verificar_acceso_calendarios(rapido=False)
        if not recuperados:
            logger.info("Keepalive calendario: conexión recuperada")
        else:
            logger.warning("Keepalive calendario: siguen fallando %s", recuperados)
    except Exception as e:
        logger.warning("Keepalive calendario error: %s", e)
        reset_google_clients()


def procesar_cola_background():
    from message_queue import limpiar_antiguos, procesar_cola, reintentar_fallidos

    n = procesar_cola(max_items=5)
    if n:
        logger.info("Cola procesada: %s mensajes", n)
    reintentar_fallidos(3)
    limpiar_antiguos(7)


def renotificar_escalaciones_background():
    from tools import renotificar_escalaciones_pendientes

    n = renotificar_escalaciones_pendientes()
    if n:
        logger.info("Escalaciones re-notificadas: %s", n)


def backup_db_background():
    """Backup diario de alessia.db (3:00 am México)."""
    ahora = datetime.datetime.now(ZONA)
    if ahora.hour != 3 or ahora.minute > 14:
        return
    clave = f"backup_{ahora.strftime('%Y-%m-%d')}"
    if storage.recordatorio_ya_enviado(clave, "global"):
        return
    try:
        from pathlib import Path
        import shutil

        src = Path(config.DATABASE_PATH)
        if not src.is_file():
            return
        dest_dir = Path(config.BACKUP_DIR)
        dest_dir.mkdir(parents=True, exist_ok=True)
        stamp = ahora.strftime("%Y%m%d_%H%M%S")
        dest = dest_dir / f"alessia_{stamp}.db"
        shutil.copy2(src, dest)
        backups = sorted(dest_dir.glob("alessia_*.db"), key=lambda p: p.stat().st_mtime)
        for viejo in backups[:-14]:
            viejo.unlink(missing_ok=True)
        storage.marcar_recordatorio_enviado(clave, "global")
        logger.info("Backup DB creado: %s", dest)
    except Exception as e:
        logger.error("Error backup DB: %s", e)


def sincronizar_catalogo_web_background():
    """Sincroniza pestaña Catalogo en Google Sheets con inpulso43.com."""
    try:
        from catalogo_sync import sincronizar_catalogo_desde_web

        sincronizar_catalogo_desde_web(forzar_lectura_web=True)
    except Exception as e:
        logger.error("Error sync catálogo web: %s", e)


def sincronizar_web_background():
    """Compara catálogo local vs inpulso43.com y alerta si hay diferencias."""
    ahora = datetime.datetime.now(ZONA)
    if ahora.hour != 6 or ahora.minute > 14:
        return
    clave = f"web_sync_{ahora.strftime('%Y-%m-%d')}"
    if storage.recordatorio_ya_enviado(clave, "global"):
        return
    try:
        from catalogo_web import TALLERES_WEB

        url = config.CLINICA_WEB_URL.rstrip("/") + "/talleres.php"
        res = requests.get(url, timeout=30, headers={"User-Agent": "AlessiaBot/1.0"})
        if res.status_code != 200:
            logger.warning("Web sync: HTTP %s", res.status_code)
            return
        html = res.text.lower()
        faltantes = []
        for t in TALLERES_WEB:
            clave_t = (t.get("nombre_corto_web") or t["nombre"]).lower()
            if clave_t[:12] not in html and t["nombre"].lower()[:12] not in html:
                faltantes.append(t["nombre"])
        if faltantes:
            logger.warning("Web sync: talleres no encontrados en web: %s", faltantes)
            destino = config.RECEPCION_WHATSAPP or config.TERAPEUTAS_WHATSAPP.get("sara")
            if destino:
                msg = (
                    f"⚠️ *Sync web inpulso43.com*\n"
                    f"Estos talleres del catálogo local no aparecen en la web:\n"
                    + "\n".join(f"• {n}" for n in faltantes)
                    + "\n\nRevisa catalogo_web.py o la web."
                )
                enviar_mensaje_whatsapp(destino, msg)
        storage.marcar_recordatorio_enviado(clave, "global")
    except Exception as e:
        logger.error("Error sync web: %s", e)
