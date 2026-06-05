"""Modo staff: terapeutas identificados por WhatsApp."""
import logging

import config
import storage
from catalogo import (
    agregar_entrada_catalogo,
    actualizar_entrada_catalogo,
    desactivar_entrada_catalogo,
    listar_catalogo_terapeuta,
)
from google_client import get_sheets_service
from tools import bloquear_horario_calendario, consultar_agenda, listar_citas_agendadas_dia

logger = logging.getLogger(__name__)


def identificar_terapeuta(telefono: str) -> str | None:
    return config.identificar_terapeuta(telefono)


def _solo_terapeuta(telefono: str) -> str:
    nombre = identificar_terapeuta(telefono)
    if not nombre:
        raise PermissionError("Número no autorizado como terapeuta.")
    return nombre


def terapeuta_mi_catalogo(telefono: str):
    """Lista talleres publicados del terapeuta."""
    nombre = _solo_terapeuta(telefono)
    filas = listar_catalogo_terapeuta(nombre, incluir_inactivos=True)
    if not filas:
        return f"{nombre} no tiene entradas en el catálogo."
    resumen = []
    for f in filas:
        estado = "activo" if f.get("activo", True) else "inactivo"
        resumen.append(
            f"[{estado}] {f['tipo']}: {f['nombre']} — {f.get('precio', '')} "
            f"({f.get('fechas', '')} {f.get('horario', '')})".strip()
        )
    return f"Catálogo de {nombre}:\n" + "\n".join(resumen)


def terapeuta_publicar_taller(
    telefono: str,
    nombre_taller: str,
    fechas: str,
    horario: str,
    precio: str,
    modalidad: str = "Presencial en Inpulso 43 y online",
    cupo: str = "Cupo limitado",
    temario: str = "",
):
    """Publica un taller nuevo en el catálogo."""
    nombre = _solo_terapeuta(telefono)
    ok, msg = agregar_entrada_catalogo(
        terapeuta=nombre,
        tipo="taller",
        nombre=nombre_taller,
        fechas=fechas,
        horario=horario,
        modalidad=modalidad,
        precio=precio,
        cupo=cupo,
        temario=temario,
    )
    if ok:
        from experiencia import clave_taller, notificar_interesados_nuevo_taller

        fila = {
            "terapeuta": nombre,
            "tipo": "taller",
            "nombre": nombre_taller,
            "fechas": fechas,
            "horario": horario,
            "modalidad": modalidad,
            "precio": precio,
            "cupo": cupo,
            "temario": temario,
        }
        storage.marcar_taller_catalogo_visto(clave_taller(fila))
        notificados = notificar_interesados_nuevo_taller(fila)
        extra = (
            f" Se notificó a {notificados} persona(s) con interés registrado."
            if notificados
            else ""
        )
        return f"ÉXITO: Taller publicado. {msg}{extra}"
    return f"ERROR: {msg}"


def terapeuta_actualizar_taller(
    telefono: str,
    nombre: str,
    fechas: str = "",
    horario: str = "",
    precio: str = "",
    cupo: str = "",
    temario: str = "",
):
    """Actualiza un taller (no precios de consultas — solo talleres)."""
    nombre_terapeuta = _solo_terapeuta(telefono)
    campos = {k: v for k, v in {
        "fechas": fechas, "horario": horario, "precio": precio,
        "cupo": cupo, "temario": temario,
    }.items() if v}
    if not campos:
        return "ERROR: Indica al menos un campo a actualizar."
    ok, msg = actualizar_entrada_catalogo(nombre_terapeuta, nombre, campos)
    return f"ÉXITO: {msg}" if ok else f"ERROR: {msg}"


def terapeuta_desactivar(telefono: str, nombre: str):
    """Oculta un taller del catálogo."""
    nombre_terapeuta = _solo_terapeuta(telefono)
    ok, msg = desactivar_entrada_catalogo(nombre_terapeuta, nombre)
    return f"ÉXITO: {msg}" if ok else f"ERROR: {msg}"


def terapeuta_consultar_disponibilidad(telefono: str, fecha: str):
    """Horarios LIBRES (huecos para agendar) — NO son citas con pacientes."""
    return consultar_agenda(fecha, _solo_terapeuta(telefono))


def terapeuta_ver_citas_agendadas(telefono: str, fecha: str):
    """Citas YA AGENDADAS con pacientes en una fecha (YYYY-MM-DD)."""
    nombre = _solo_terapeuta(telefono)
    return listar_citas_agendadas_dia(nombre, fecha)


def terapeuta_consultar_agenda(telefono: str, fecha: str):
    """Alias legacy — preferir terapeuta_ver_citas_agendadas o terapeuta_consultar_disponibilidad."""
    return terapeuta_ver_citas_agendadas(telefono, fecha)


def terapeuta_bloquear_horario(
    telefono: str,
    fecha_hora_inicio: str,
    fecha_hora_fin: str,
    motivo: str = "No disponible",
):
    """Bloquea horario en Google Calendar."""
    nombre = _solo_terapeuta(telefono)
    return bloquear_horario_calendario(nombre, fecha_hora_inicio, fecha_hora_fin, motivo)


def terapeuta_asignar_tarea(
    telefono: str,
    telefono_paciente: str,
    descripcion: str,
    dias_semana: str = "lunes,martes,miercoles,jueves,viernes",
):
    """Asigna tarea terapéutica al paciente con recordatorios entre sesiones."""
    _solo_terapeuta(telefono)
    if not telefono_paciente or not descripcion.strip():
        return "ERROR: Indica teléfono del paciente y descripción de la tarea."
    tarea_id = storage.crear_tarea_terapeutica(
        telefono_paciente.strip(),
        telefono.strip(),
        descripcion.strip(),
        dias_semana.strip(),
    )
    return (
        f"ÉXITO: Tarea #{tarea_id} asignada. "
        f"El paciente recibirá recordatorios los días: {dias_semana}."
    )


def terapeuta_ver_inscritos(telefono: str, nombre_taller: str):
    """Lista inscritos a un taller."""
    _solo_terapeuta(telefono)
    if not config.ID_HOJA_CALCULO:
        return "ERROR: Hoja no configurada."
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=config.ID_HOJA_CALCULO, range="Inscripciones!A:F"
        ).execute()
        taller_lower = nombre_taller.lower()
        inscritos = [
            f"{r[1]} — {r[2]} — {r[5] if len(r) > 5 else '?'}"
            for r in result.get("values", [])[1:]
            if len(r) >= 5 and taller_lower in r[4].lower()
        ]
        return (
            f"Inscritos a '{nombre_taller}':\n" + "\n".join(inscritos)
            if inscritos else f"No hay inscritos para '{nombre_taller}'."
        )
    except Exception as e:
        logger.error("Error inscritos: %s", e)
        return "ERROR leyendo inscripciones."
