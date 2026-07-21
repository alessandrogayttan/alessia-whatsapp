import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

_lock = threading.Lock()


def _utcnow() -> datetime:
    """UTC naive (mismo contrato que utcnow; evita mezclar aware/naive en SQLite)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)



def _ensure_db_dir():
    Path(config.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)


def _connect():
    _ensure_db_dir()
    conn = sqlite3.connect(config.DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def ping_db() -> bool:
    """Verifica que la base SQLite responde."""
    try:
        with _transaction() as conn:
            conn.execute("SELECT 1")
        return True
    except sqlite3.Error:
        return False


def init_db():
    with _lock:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mensajes_procesados (
                    mensaje_id TEXT PRIMARY KEY,
                    procesado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recordatorios_enviados (
                    event_id TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    enviado_at TEXT NOT NULL,
                    PRIMARY KEY (event_id, tipo)
                );
                CREATE TABLE IF NOT EXISTS ubicaciones_pacientes (
                    telefono TEXT PRIMARY KEY,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    actualizado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pacientes (
                    telefono TEXT PRIMARY KEY,
                    consentimiento_at TEXT,
                    nombre TEXT
                );
                CREATE TABLE IF NOT EXISTS menciones_cita_proactiva (
                    telefono TEXT NOT NULL,
                    cita_clave TEXT NOT NULL,
                    mencionado_at TEXT NOT NULL,
                    PRIMARY KEY (telefono, cita_clave)
                );
                CREATE TABLE IF NOT EXISTS paciente_extra (
                    telefono TEXT PRIMARY KEY,
                    citas_completadas INTEGER DEFAULT 0,
                    nps_enviado INTEGER DEFAULT 0,
                    primera_vez INTEGER DEFAULT 1,
                    frase_dia INTEGER DEFAULT 0,
                    codigo_referido TEXT UNIQUE,
                    referido_por TEXT,
                    ultimo_animo INTEGER,
                    ultima_trivia_semana INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS checkins_emocionales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telefono TEXT NOT NULL,
                    event_id TEXT,
                    escala INTEGER,
                    notas TEXT,
                    creado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS referidos_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL,
                    telefono_nuevo TEXT NOT NULL,
                    creado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS prep_sesion (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telefono TEXT NOT NULL,
                    event_id TEXT,
                    tema TEXT,
                    es_primera TEXT,
                    animo INTEGER,
                    creado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS prep_pendiente (
                    telefono TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    creado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ritual_pendiente (
                    telefono TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    creado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notas_ritual (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telefono TEXT NOT NULL,
                    event_id TEXT,
                    nota TEXT NOT NULL,
                    creado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS primera_cita (
                    telefono TEXT PRIMARY KEY,
                    fecha TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS aniversarios_enviados (
                    telefono TEXT NOT NULL,
                    anio INTEGER NOT NULL,
                    enviado_at TEXT NOT NULL,
                    PRIMARY KEY (telefono, anio)
                );
                CREATE TABLE IF NOT EXISTS taller_bienvenida (
                    clave TEXT PRIMARY KEY,
                    enviado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tareas_terapeuticas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telefono_paciente TEXT NOT NULL,
                    telefono_terapeuta TEXT NOT NULL,
                    descripcion TEXT NOT NULL,
                    dias_semana TEXT NOT NULL,
                    activa INTEGER DEFAULT 1,
                    ultimo_envio TEXT,
                    creado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS interes_talleres (
                    telefono TEXT NOT NULL,
                    terapeuta TEXT NOT NULL,
                    nombre TEXT,
                    taller_origen TEXT,
                    creado_at TEXT NOT NULL,
                    activo INTEGER DEFAULT 1,
                    PRIMARY KEY (telefono, terapeuta)
                );
                CREATE TABLE IF NOT EXISTS catalogo_talleres_vistos (
                    clave TEXT PRIMARY KEY,
                    visto_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notificaciones_nuevo_taller (
                    telefono TEXT NOT NULL,
                    taller_clave TEXT NOT NULL,
                    enviado_at TEXT NOT NULL,
                    PRIMARY KEY (telefono, taller_clave)
                );
                CREATE TABLE IF NOT EXISTS cola_mensajes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telefono TEXT NOT NULL,
                    contenido TEXT NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'pendiente',
                    intentos INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    creado_at TEXT NOT NULL,
                    actualizado_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cola_estado ON cola_mensajes(estado, creado_at);
                CREATE TABLE IF NOT EXISTS confirmaciones_asistencia (
                    event_id TEXT NOT NULL,
                    telefono TEXT NOT NULL,
                    fecha_cita TEXT,
                    hora_cita TEXT,
                    especialista TEXT,
                    confirmado_at TEXT NOT NULL,
                    PRIMARY KEY (event_id, telefono)
                );
                CREATE TABLE IF NOT EXISTS reagendar_pendiente (
                    telefono TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    creado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS nps_pendiente (
                    telefono TEXT PRIMARY KEY,
                    event_id TEXT,
                    creado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS nps_respuestas (
                    telefono TEXT PRIMARY KEY,
                    puntaje INTEGER NOT NULL,
                    event_id TEXT,
                    respondido_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recibo_folio_seq (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    ultimo INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS recibos_pago (
                    folio TEXT PRIMARY KEY,
                    telefono TEXT NOT NULL,
                    nombre TEXT,
                    concepto TEXT,
                    monto REAL NOT NULL,
                    enviado_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS web_chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    telefono_vinculado TEXT,
                    nombre TEXT,
                    creado_at TEXT NOT NULL,
                    ultimo_mensaje_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS web_chat_hits (
                    ip_hash TEXT NOT NULL,
                    minuto TEXT NOT NULL,
                    hits INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (ip_hash, minuto)
                );
                CREATE TABLE IF NOT EXISTS conversacion_mensajes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clave TEXT NOT NULL,
                    canal TEXT NOT NULL,
                    rol TEXT NOT NULL,
                    contenido TEXT NOT NULL,
                    creado_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conversacion_clave
                    ON conversacion_mensajes(clave, id);
                CREATE TABLE IF NOT EXISTS equipo_acceso (
                    telefono TEXT PRIMARY KEY,
                    sesion_activa INTEGER NOT NULL DEFAULT 0,
                    esperando_clave INTEGER NOT NULL DEFAULT 0,
                    nombre_miembro TEXT,
                    expira_at TEXT,
                    actualizado_at TEXT
                );
                CREATE TABLE IF NOT EXISTS escalaciones_local (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telefono TEXT NOT NULL,
                    nombre TEXT,
                    motivo TEXT NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'PENDIENTE',
                    notificado INTEGER NOT NULL DEFAULT 0,
                    creado_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_escalaciones_estado
                    ON escalaciones_local(estado, creado_at);
                CREATE TABLE IF NOT EXISTS equipo_clave_intentos (
                    telefono TEXT PRIMARY KEY,
                    fallos INTEGER NOT NULL DEFAULT 0,
                    bloqueado_hasta TEXT,
                    actualizado_at TEXT
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS inpulso_rag_fts USING fts5(
                    fuente,
                    url,
                    chunk,
                    tokenize='unicode61 remove_diacritics 2'
                );
                """
            )
            conn.commit()
        finally:
            conn.close()


@contextmanager
def _transaction():
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def reservar_mensaje_para_procesar(mensaje_id: str) -> bool:
    """Atómico: True solo la primera vez que llega este id (evita respuestas duplicadas)."""
    with _transaction() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO mensajes_procesados (mensaje_id, procesado_at) VALUES (?, ?)",
            (mensaje_id, _utcnow().isoformat()),
        )
        if cur.rowcount == 0:
            return False
        cutoff = (_utcnow() - timedelta(days=7)).isoformat()
        conn.execute(
            "DELETE FROM mensajes_procesados WHERE procesado_at < ?",
            (cutoff,),
        )
        return True


def recordatorio_ya_enviado(event_id: str, tipo: str) -> bool:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT 1 FROM recordatorios_enviados WHERE event_id = ? AND tipo = ?",
            (event_id, tipo),
        ).fetchone()
        return row is not None


def marcar_recordatorio_enviado(event_id: str, tipo: str):
    with _transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO recordatorios_enviados (event_id, tipo, enviado_at) VALUES (?, ?, ?)",
            (event_id, tipo, _utcnow().isoformat()),
        )


def guardar_ubicacion(telefono: str, lat: float, lng: float):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO ubicaciones_pacientes (telefono, lat, lng, actualizado_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telefono) DO UPDATE SET
                lat = excluded.lat,
                lng = excluded.lng,
                actualizado_at = excluded.actualizado_at
            """,
            (telefono, lat, lng, _utcnow().isoformat()),
        )


def obtener_ubicacion(telefono: str) -> str | None:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT lat, lng FROM ubicaciones_pacientes WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        if row:
            return f"{row['lat']},{row['lng']}"
        return None


def paciente_registrado(telefono: str) -> bool:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT consentimiento_at FROM pacientes WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row is not None and row["consentimiento_at"] is not None


def registrar_consentimiento(telefono: str):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO pacientes (telefono, consentimiento_at)
            VALUES (?, ?)
            ON CONFLICT(telefono) DO UPDATE SET consentimiento_at = excluded.consentimiento_at
            """,
            (telefono, _utcnow().isoformat()),
        )


def eliminar_datos_paciente(telefono: str):
    with _transaction() as conn:
        conn.execute("DELETE FROM pacientes WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM ubicaciones_pacientes WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM menciones_cita_proactiva WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM paciente_extra WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM checkins_emocionales WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM prep_sesion WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM prep_pendiente WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM ritual_pendiente WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM notas_ritual WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM primera_cita WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM aniversarios_enviados WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM tareas_terapeuticas WHERE telefono_paciente = ?", (telefono,))
        conn.execute("DELETE FROM interes_talleres WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM notificaciones_nuevo_taller WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM referidos_log WHERE telefono_nuevo = ?", (telefono,))
        conn.execute("DELETE FROM nps_pendiente WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM nps_respuestas WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM reagendar_pendiente WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM confirmaciones_asistencia WHERE telefono = ?", (telefono,))
        conn.execute("DELETE FROM recibos_pago WHERE telefono = ?", (telefono,))


def ya_menciono_cita_proactiva(telefono: str, cita_clave: str) -> bool:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT 1 FROM menciones_cita_proactiva WHERE telefono = ? AND cita_clave = ?",
            (telefono, cita_clave),
        ).fetchone()
        return row is not None


def marcar_cita_proactiva_mencionada(telefono: str, cita_clave: str):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO menciones_cita_proactiva (telefono, cita_clave, mencionado_at)
            VALUES (?, ?, ?)
            ON CONFLICT(telefono, cita_clave) DO UPDATE SET mencionado_at = excluded.mencionado_at
            """,
            (telefono, cita_clave, _utcnow().isoformat()),
        )


def resetear_menciones_proactivas(telefono: str):
    """Borra recordatorios proactivos al cancelar o reagendar (punto 13)."""
    with _transaction() as conn:
        conn.execute(
            "DELETE FROM menciones_cita_proactiva WHERE telefono = ?",
            (telefono,),
        )


def guardar_nombre_paciente(telefono: str, nombre: str):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO pacientes (telefono, nombre, consentimiento_at)
            VALUES (?, ?, ?)
            ON CONFLICT(telefono) DO UPDATE SET nombre = excluded.nombre
            """,
            (telefono, nombre, _utcnow().isoformat()),
        )


def obtener_nombre_paciente(telefono: str) -> str | None:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT nombre FROM pacientes WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        if row and row["nombre"]:
            return row["nombre"]
        return None


def primer_nombre(telefono: str) -> str | None:
    """Primer nombre guardado (memoria permanente por teléfono)."""
    nombre = obtener_nombre_paciente(telefono)
    if not nombre:
        return None
    return nombre.strip().split()[0]


def tiene_nombre_completo(telefono: str) -> bool:
    nombre = obtener_nombre_paciente(telefono)
    return bool(nombre and len(nombre.split()) >= 2)


def guardar_nombre_casual(telefono: str, nombre: str):
    """Guarda primer nombre; no sobrescribe un nombre completo ya registrado."""
    nombre = " ".join(nombre.strip().split())
    if not nombre or len(nombre) < 2:
        return
    actual = obtener_nombre_paciente(telefono)
    if actual and len(actual.split()) >= 2:
        return
    if actual and len(nombre.split()) <= len(actual.split()):
        return
    guardar_nombre_paciente(telefono, nombre)


def _ensure_extra(conn, telefono: str):
    conn.execute(
        "INSERT OR IGNORE INTO paciente_extra (telefono) VALUES (?)",
        (telefono,),
    )


def es_primera_vez(telefono: str) -> bool:
    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        row = conn.execute(
            "SELECT primera_vez FROM paciente_extra WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row is None or row["primera_vez"] == 1


def marcar_no_primera_vez(telefono: str):
    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        conn.execute(
            "UPDATE paciente_extra SET primera_vez = 0 WHERE telefono = ?",
            (telefono,),
        )


def frase_dia_activa(telefono: str) -> bool:
    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        row = conn.execute(
            "SELECT frase_dia FROM paciente_extra WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row and row["frase_dia"] == 1


def activar_frase_dia(telefono: str, activo: bool):
    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        conn.execute(
            "UPDATE paciente_extra SET frase_dia = ? WHERE telefono = ?",
            (1 if activo else 0, telefono),
        )


def obtener_o_crear_codigo_referido(telefono: str) -> str:
    import secrets

    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        row = conn.execute(
            "SELECT codigo_referido FROM paciente_extra WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        if row and row["codigo_referido"]:
            return row["codigo_referido"]
        codigo = f"INPULSO-{secrets.token_hex(3).upper()}"
        conn.execute(
            "UPDATE paciente_extra SET codigo_referido = ? WHERE telefono = ?",
            (codigo, telefono),
        )
        return codigo


def registrar_uso_referido(codigo: str, telefono_nuevo: str) -> bool:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT telefono FROM paciente_extra WHERE codigo_referido = ?",
            (codigo.upper(),),
        ).fetchone()
        if not row:
            return False
        dup = conn.execute(
            "SELECT 1 FROM referidos_log WHERE telefono_nuevo = ?",
            (telefono_nuevo,),
        ).fetchone()
        if dup:
            return False
        conn.execute(
            "INSERT INTO referidos_log (codigo, telefono_nuevo, creado_at) VALUES (?, ?, ?)",
            (codigo.upper(), telefono_nuevo, _utcnow().isoformat()),
        )
        _ensure_extra(conn, telefono_nuevo)
        conn.execute(
            "UPDATE paciente_extra SET referido_por = ? WHERE telefono = ?",
            (codigo.upper(), telefono_nuevo),
        )
        return True


def guardar_checkin_emocional(telefono: str, escala: int, event_id: str = "", notas: str = ""):
    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        conn.execute(
            "INSERT INTO checkins_emocionales (telefono, event_id, escala, notas, creado_at) VALUES (?, ?, ?, ?, ?)",
            (telefono, event_id, escala, notas, _utcnow().isoformat()),
        )
        conn.execute(
            "UPDATE paciente_extra SET ultimo_animo = ? WHERE telefono = ?",
            (escala, telefono),
        )


def incrementar_citas_completadas(telefono: str) -> int:
    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        conn.execute(
            "UPDATE paciente_extra SET citas_completadas = citas_completadas + 1 WHERE telefono = ?",
            (telefono,),
        )
        row = conn.execute(
            "SELECT citas_completadas FROM paciente_extra WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row["citas_completadas"] if row else 0


def marcar_nps_enviado(telefono: str):
    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        conn.execute(
            "UPDATE paciente_extra SET nps_enviado = 1 WHERE telefono = ?",
            (telefono,),
        )


def nps_ya_enviado(telefono: str) -> bool:
    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        row = conn.execute(
            "SELECT nps_enviado FROM paciente_extra WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row and row["nps_enviado"] == 1


def citas_completadas(telefono: str) -> int:
    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        row = conn.execute(
            "SELECT citas_completadas FROM paciente_extra WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row["citas_completadas"] if row else 0


def pacientes_frase_dia_activa() -> list[str]:
    with _transaction() as conn:
        rows = conn.execute(
            "SELECT telefono FROM paciente_extra WHERE frase_dia = 1"
        ).fetchall()
        return [r["telefono"] for r in rows]


def marcar_trivia_enviada(telefono: str, semana: int):
    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        conn.execute(
            "UPDATE paciente_extra SET ultima_trivia_semana = ? WHERE telefono = ?",
            (semana, telefono),
        )


def trivia_enviada_esta_semana(telefono: str, semana: int) -> bool:
    with _transaction() as conn:
        _ensure_extra(conn, telefono)
        row = conn.execute(
            "SELECT ultima_trivia_semana FROM paciente_extra WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row and row["ultima_trivia_semana"] == semana


def telefonos_pacientes_con_nombre() -> list[str]:
    with _transaction() as conn:
        rows = conn.execute(
            "SELECT telefono FROM pacientes WHERE nombre IS NOT NULL AND nombre != ''"
        ).fetchall()
        return [r["telefono"] for r in rows]


def estadisticas_globales() -> dict:
    mes = _utcnow().strftime("%Y-%m")
    with _transaction() as conn:
        pacientes = conn.execute("SELECT COUNT(*) AS c FROM pacientes").fetchone()["c"]
        referidos = conn.execute("SELECT COUNT(*) AS c FROM referidos_log").fetchone()["c"]
        checkins = conn.execute(
            "SELECT COUNT(*) AS c FROM checkins_emocionales WHERE creado_at LIKE ?",
            (f"{mes}%",),
        ).fetchone()["c"]
        return {"pacientes": pacientes, "referidos": referidos, "checkins_mes": checkins}


def obtener_ultimo_animo(telefono: str) -> int | None:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT ultimo_animo FROM paciente_extra WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row["ultimo_animo"] if row and row["ultimo_animo"] is not None else None


def marcar_prep_pendiente(telefono: str, event_id: str):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO prep_pendiente (telefono, event_id, creado_at)
            VALUES (?, ?, ?)
            ON CONFLICT(telefono) DO UPDATE SET
                event_id = excluded.event_id,
                creado_at = excluded.creado_at
            """,
            (telefono, event_id, _utcnow().isoformat()),
        )


def obtener_prep_pendiente(telefono: str) -> str | None:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT event_id FROM prep_pendiente WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row["event_id"] if row else None


def limpiar_prep_pendiente(telefono: str):
    with _transaction() as conn:
        conn.execute("DELETE FROM prep_pendiente WHERE telefono = ?", (telefono,))


def asistencia_ya_confirmada(event_id: str, telefono: str) -> bool:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT 1 FROM confirmaciones_asistencia WHERE event_id = ? AND telefono = ?",
            (event_id, telefono),
        ).fetchone()
        return row is not None


def marcar_asistencia_confirmada(
    telefono: str,
    event_id: str,
    fecha_cita: str = "",
    hora_cita: str = "",
    especialista: str = "",
):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO confirmaciones_asistencia
            (event_id, telefono, fecha_cita, hora_cita, especialista, confirmado_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                telefono,
                fecha_cita,
                hora_cita,
                especialista,
                _utcnow().isoformat(),
            ),
        )


def marcar_reagendar_pendiente(telefono: str, event_id: str):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO reagendar_pendiente (telefono, event_id, creado_at)
            VALUES (?, ?, ?)
            ON CONFLICT(telefono) DO UPDATE SET
                event_id = excluded.event_id,
                creado_at = excluded.creado_at
            """,
            (telefono, event_id, _utcnow().isoformat()),
        )


def obtener_reagendar_pendiente(telefono: str) -> str | None:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT event_id FROM reagendar_pendiente WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row["event_id"] if row else None


def limpiar_reagendar_pendiente(telefono: str):
    with _transaction() as conn:
        conn.execute("DELETE FROM reagendar_pendiente WHERE telefono = ?", (telefono,))


def marcar_nps_pendiente(telefono: str, event_id: str = ""):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO nps_pendiente (telefono, event_id, creado_at)
            VALUES (?, ?, ?)
            ON CONFLICT(telefono) DO UPDATE SET
                event_id = excluded.event_id,
                creado_at = excluded.creado_at
            """,
            (telefono, event_id, _utcnow().isoformat()),
        )


def obtener_nps_pendiente(telefono: str) -> bool:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT 1 FROM nps_pendiente WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row is not None


def limpiar_nps_pendiente(telefono: str):
    with _transaction() as conn:
        conn.execute("DELETE FROM nps_pendiente WHERE telefono = ?", (telefono,))


def guardar_respuesta_nps(telefono: str, puntaje: int, event_id: str = ""):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO nps_respuestas (telefono, puntaje, event_id, respondido_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telefono) DO UPDATE SET
                puntaje = excluded.puntaje,
                event_id = excluded.event_id,
                respondido_at = excluded.respondido_at
            """,
            (telefono, puntaje, event_id, _utcnow().isoformat()),
        )
        conn.execute("DELETE FROM nps_pendiente WHERE telefono = ?", (telefono,))


def obtener_ultimo_nps(telefono: str) -> int | None:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT puntaje FROM nps_respuestas WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row["puntaje"] if row else None


def siguiente_folio_recibo() -> str:
    with _transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO recibo_folio_seq (id, ultimo) VALUES (1, 0)")
        conn.execute("UPDATE recibo_folio_seq SET ultimo = ultimo + 1 WHERE id = 1")
        row = conn.execute("SELECT ultimo FROM recibo_folio_seq WHERE id = 1").fetchone()
        return f"INP-{row['ultimo']:06d}"


def registrar_recibo_enviado(
    folio: str,
    telefono: str,
    nombre: str,
    concepto: str,
    monto: float,
):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO recibos_pago (folio, telefono, nombre, concepto, monto, enviado_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                folio,
                telefono,
                nombre,
                concepto,
                monto,
                _utcnow().isoformat(),
            ),
        )


def guardar_prep_sesion(
    telefono: str,
    event_id: str,
    tema: str,
    es_primera: str = "",
    animo: int = 0,
):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO prep_sesion (telefono, event_id, tema, es_primera, animo, creado_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                telefono,
                event_id,
                tema,
                es_primera,
                animo or None,
                _utcnow().isoformat(),
            ),
        )
        conn.execute("DELETE FROM prep_pendiente WHERE telefono = ?", (telefono,))


def obtener_prep_sesion_reciente(telefono: str) -> dict | None:
    with _transaction() as conn:
        row = conn.execute(
            """
            SELECT tema, es_primera, animo FROM prep_sesion
            WHERE telefono = ? ORDER BY creado_at DESC LIMIT 1
            """,
            (telefono,),
        ).fetchone()
        if not row:
            return None
        return {
            "tema": row["tema"] or "",
            "es_primera": row["es_primera"] or "",
            "animo": row["animo"],
        }


def marcar_ritual_pendiente(telefono: str, event_id: str):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO ritual_pendiente (telefono, event_id, creado_at)
            VALUES (?, ?, ?)
            ON CONFLICT(telefono) DO UPDATE SET
                event_id = excluded.event_id,
                creado_at = excluded.creado_at
            """,
            (telefono, event_id, _utcnow().isoformat()),
        )


def obtener_ritual_pendiente(telefono: str) -> str | None:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT event_id FROM ritual_pendiente WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row["event_id"] if row else None


def limpiar_ritual_pendiente(telefono: str):
    with _transaction() as conn:
        conn.execute("DELETE FROM ritual_pendiente WHERE telefono = ?", (telefono,))


def guardar_nota_ritual(telefono: str, event_id: str, nota: str):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO notas_ritual (telefono, event_id, nota, creado_at)
            VALUES (?, ?, ?, ?)
            """,
            (telefono, event_id, nota, _utcnow().isoformat()),
        )
        conn.execute("DELETE FROM ritual_pendiente WHERE telefono = ?", (telefono,))


def registrar_primera_cita_si_nueva(telefono: str, fecha: str):
    with _transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO primera_cita (telefono, fecha) VALUES (?, ?)",
            (telefono, fecha[:10]),
        )


def listar_primeras_citas() -> list[tuple[str, str]]:
    with _transaction() as conn:
        rows = conn.execute("SELECT telefono, fecha FROM primera_cita").fetchall()
        return [(r["telefono"], r["fecha"]) for r in rows]


def aniversario_ya_enviado(telefono: str, anio: int) -> bool:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT 1 FROM aniversarios_enviados WHERE telefono = ? AND anio = ?",
            (telefono, anio),
        ).fetchone()
        return row is not None


def marcar_aniversario_enviado(telefono: str, anio: int):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO aniversarios_enviados (telefono, anio, enviado_at)
            VALUES (?, ?, ?)
            """,
            (telefono, anio, _utcnow().isoformat()),
        )


def taller_bienvenida_enviada(clave: str) -> bool:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT 1 FROM taller_bienvenida WHERE clave = ?",
            (clave,),
        ).fetchone()
        return row is not None


def marcar_taller_bienvenida(clave: str):
    with _transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO taller_bienvenida (clave, enviado_at) VALUES (?, ?)",
            (clave, _utcnow().isoformat()),
        )


def crear_tarea_terapeutica(
    telefono_paciente: str,
    telefono_terapeuta: str,
    descripcion: str,
    dias_semana: str,
) -> int:
    with _transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO tareas_terapeuticas
            (telefono_paciente, telefono_terapeuta, descripcion, dias_semana, creado_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                telefono_paciente,
                telefono_terapeuta,
                descripcion,
                dias_semana.lower(),
                _utcnow().isoformat(),
            ),
        )
        return cur.lastrowid


def tareas_pendientes_hoy(dia_nombre: str) -> list[dict]:
    hoy = _utcnow().strftime("%Y-%m-%d")
    with _transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, telefono_paciente AS telefono, descripcion
            FROM tareas_terapeuticas
            WHERE activa = 1
              AND (ultimo_envio IS NULL OR ultimo_envio != ?)
              AND dias_semana LIKE ?
            """,
            (hoy, f"%{dia_nombre.lower()}%"),
        ).fetchall()
        return [dict(r) for r in rows]


def registrar_interes_taller(
    telefono: str,
    terapeuta: str,
    taller_origen: str = "",
    nombre: str = "",
):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO interes_talleres (telefono, terapeuta, nombre, taller_origen, creado_at, activo)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(telefono, terapeuta) DO UPDATE SET
                nombre = excluded.nombre,
                taller_origen = excluded.taller_origen,
                activo = 1
            """,
            (
                telefono,
                terapeuta.strip(),
                nombre or None,
                taller_origen or None,
                _utcnow().isoformat(),
            ),
        )


def listar_interes_talleres(terapeuta: str) -> list[dict]:
    t_lower = terapeuta.lower().strip()
    with _transaction() as conn:
        rows = conn.execute(
            """
            SELECT telefono, nombre, terapeuta, taller_origen
            FROM interes_talleres WHERE activo = 1
            """
        ).fetchall()
    resultado = []
    for r in rows:
        row = dict(r)
        esp = (row.get("terapeuta") or "").lower()
        if t_lower in esp or esp in t_lower or _coincide_terapeuta(t_lower, esp):
            resultado.append(row)
    return resultado


def _coincide_terapeuta(a: str, b: str) -> bool:
    """Compara por primer nombre si los apellidos varían (Sara vs Sara Rosales)."""
    pa = a.split()
    pb = b.split()
    return bool(pa and pb and pa[0] == pb[0])


def contar_talleres_catalogo_vistos() -> int:
    with _transaction() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM catalogo_talleres_vistos").fetchone()
        return int(row["n"]) if row else 0


def taller_catalogo_ya_visto(clave: str) -> bool:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT 1 FROM catalogo_talleres_vistos WHERE clave = ?",
            (clave,),
        ).fetchone()
        return row is not None


def marcar_taller_catalogo_visto(clave: str):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO catalogo_talleres_vistos (clave, visto_at)
            VALUES (?, ?)
            """,
            (clave, _utcnow().isoformat()),
        )


def notificacion_nuevo_taller_enviada(telefono: str, taller_clave: str) -> bool:
    with _transaction() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM notificaciones_nuevo_taller
            WHERE telefono = ? AND taller_clave = ?
            """,
            (telefono, taller_clave),
        ).fetchone()
        return row is not None


def marcar_notificacion_nuevo_taller(telefono: str, taller_clave: str):
    with _transaction() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO notificaciones_nuevo_taller (telefono, taller_clave, enviado_at)
            VALUES (?, ?, ?)
            """,
            (telefono, taller_clave, _utcnow().isoformat()),
        )


def marcar_tarea_enviada_hoy(tarea_id: int, fecha: str):
    with _transaction() as conn:
        conn.execute(
            "UPDATE tareas_terapeuticas SET ultimo_envio = ? WHERE id = ?",
            (fecha, tarea_id),
        )


def encolar_mensaje_ia(telefono: str, contenido: str) -> int:
    ahora = _utcnow().isoformat()
    with _transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO cola_mensajes (telefono, contenido, estado, intentos, creado_at, actualizado_at)
            VALUES (?, ?, 'pendiente', 0, ?, ?)
            """,
            (telefono, contenido, ahora, ahora),
        )
        return cur.lastrowid


def obtener_mensajes_pendientes(limite: int = 10) -> list[dict]:
    with _transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, telefono, contenido, intentos
            FROM cola_mensajes
            WHERE estado = 'pendiente' AND intentos < 3
            ORDER BY creado_at ASC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
        return [dict(r) for r in rows]


def marcar_mensaje_procesando(msg_id: int) -> bool:
    ahora = _utcnow().isoformat()
    with _transaction() as conn:
        cur = conn.execute(
            """
            UPDATE cola_mensajes
            SET estado = 'procesando', actualizado_at = ?
            WHERE id = ? AND estado = 'pendiente'
            """,
            (ahora, msg_id),
        )
        return cur.rowcount > 0


def marcar_mensaje_completado(msg_id: int):
    ahora = _utcnow().isoformat()
    with _transaction() as conn:
        conn.execute(
            """
            UPDATE cola_mensajes
            SET estado = 'completado', actualizado_at = ?
            WHERE id = ?
            """,
            (ahora, msg_id),
        )


def marcar_mensaje_fallido(msg_id: int, intentos: int, error: str = ""):
    ahora = _utcnow().isoformat()
    estado = "fallido" if intentos >= 3 else "pendiente"
    with _transaction() as conn:
        conn.execute(
            """
            UPDATE cola_mensajes
            SET estado = ?, intentos = ?, error = ?, actualizado_at = ?
            WHERE id = ?
            """,
            (estado, intentos, error, ahora, msg_id),
        )


def reencolar_mensajes_fallidos(limite: int = 5) -> int:
    ahora = _utcnow().isoformat()
    with _transaction() as conn:
        cur = conn.execute(
            """
            UPDATE cola_mensajes
            SET estado = 'pendiente', actualizado_at = ?
            WHERE id IN (
                SELECT id FROM cola_mensajes
                WHERE estado = 'fallido' AND intentos < 3
                ORDER BY actualizado_at ASC
                LIMIT ?
            )
            """,
            (ahora, limite),
        )
        return cur.rowcount


def limpiar_cola_antigua(cutoff_iso: str) -> int:
    with _transaction() as conn:
        cur = conn.execute(
            """
            DELETE FROM cola_mensajes
            WHERE estado = 'completado' AND actualizado_at < ?
            """,
            (cutoff_iso,),
        )
        return cur.rowcount


def contar_cola_pendiente() -> int:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM cola_mensajes WHERE estado = 'pendiente'"
        ).fetchone()
        return int(row["n"]) if row else 0


def necesita_consentimiento(telefono: str) -> bool:
    """True si el paciente aún no ha dado consentimiento explícito."""
    with _transaction() as conn:
        row = conn.execute(
            "SELECT consentimiento_at FROM pacientes WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row is None or row["consentimiento_at"] is None


def crear_sesion_web(session_id: str) -> None:
    ahora = _utcnow().isoformat()
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO web_chat_sessions (session_id, creado_at, ultimo_mensaje_at)
            VALUES (?, ?, ?)
            """,
            (session_id, ahora, ahora),
        )


def obtener_sesion_web(session_id: str) -> dict | None:
    with _transaction() as conn:
        row = conn.execute(
            """
            SELECT session_id, telefono_vinculado, nombre, creado_at, ultimo_mensaje_at
            FROM web_chat_sessions WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None


def actualizar_sesion_web(
    session_id: str,
    *,
    telefono: str | None = None,
    nombre: str | None = None,
) -> None:
    ahora = _utcnow().isoformat()
    with _transaction() as conn:
        if telefono is not None and nombre is not None:
            conn.execute(
                """
                UPDATE web_chat_sessions
                SET telefono_vinculado = ?, nombre = ?, ultimo_mensaje_at = ?
                WHERE session_id = ?
                """,
                (telefono, nombre, ahora, session_id),
            )
        elif telefono is not None:
            conn.execute(
                """
                UPDATE web_chat_sessions
                SET telefono_vinculado = ?, ultimo_mensaje_at = ?
                WHERE session_id = ?
                """,
                (telefono, ahora, session_id),
            )
        elif nombre is not None:
            conn.execute(
                """
                UPDATE web_chat_sessions
                SET nombre = ?, ultimo_mensaje_at = ?
                WHERE session_id = ?
                """,
                (nombre, ahora, session_id),
            )
        else:
            conn.execute(
                """
                UPDATE web_chat_sessions SET ultimo_mensaje_at = ? WHERE session_id = ?
                """,
                (ahora, session_id),
            )


def registrar_hit_web_chat(ip_hash: str, limite_por_minuto: int) -> bool:
    """True si el hit está permitido (bajo el rate limit)."""
    minuto = _utcnow().strftime("%Y-%m-%dT%H:%M")
    with _transaction() as conn:
        row = conn.execute(
            "SELECT hits FROM web_chat_hits WHERE ip_hash = ? AND minuto = ?",
            (ip_hash, minuto),
        ).fetchone()
        hits = int(row["hits"]) if row else 0
        if hits >= limite_por_minuto:
            return False
        conn.execute(
            """
            INSERT INTO web_chat_hits (ip_hash, minuto, hits) VALUES (?, ?, 1)
            ON CONFLICT(ip_hash, minuto) DO UPDATE SET hits = hits + 1
            """,
            (ip_hash, minuto),
        )
        return True


def guardar_mensaje_conversacion(
    clave: str,
    canal: str,
    rol: str,
    contenido: str,
) -> None:
    texto = (contenido or "").strip()
    if not texto or not clave:
        return
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO conversacion_mensajes (clave, canal, rol, contenido, creado_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (clave, canal, rol, texto[:8000], _utcnow().isoformat()),
        )


def obtener_mensajes_conversacion(clave: str, limite: int = 40) -> list[dict]:
    with _transaction() as conn:
        rows = conn.execute(
            """
            SELECT rol, contenido, canal, creado_at
            FROM conversacion_mensajes
            WHERE clave = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (clave, limite),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def migrar_conversacion_clave(clave_origen: str, clave_destino: str) -> int:
    if not clave_origen or not clave_destino or clave_origen == clave_destino:
        return 0
    with _transaction() as conn:
        cur = conn.execute(
            "UPDATE conversacion_mensajes SET clave = ? WHERE clave = ?",
            (clave_destino, clave_origen),
        )
        return cur.rowcount


def limpiar_rag_indice() -> None:
    with _transaction() as conn:
        conn.execute("DELETE FROM inpulso_rag_fts")


def insertar_chunks_rag(chunks: list[tuple[str, str, str]]) -> int:
    if not chunks:
        return 0
    with _transaction() as conn:
        conn.executemany(
            "INSERT INTO inpulso_rag_fts (fuente, url, chunk) VALUES (?, ?, ?)",
            chunks,
        )
    return len(chunks)


def buscar_rag_fts(consulta: str, limite: int = 8) -> list[dict]:
    q = (consulta or "").strip()
    if not q:
        return []
    tokens = [t for t in re.sub(r"[^\w\s]", " ", q, flags=re.UNICODE).split() if len(t) > 2]
    if not tokens:
        tokens = q.split()[:3]
    match = " OR ".join(f'"{t}"' for t in tokens[:8])
    try:
        with _transaction() as conn:
            rows = conn.execute(
                """
                SELECT fuente, url, chunk
                FROM inpulso_rag_fts
                WHERE inpulso_rag_fts MATCH ?
                LIMIT ?
                """,
                (match, limite),
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def contar_chunks_rag() -> int:
    with _transaction() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM inpulso_rag_fts").fetchone()
        return int(row["n"]) if row else 0


def _fila_equipo_acceso(telefono: str) -> dict | None:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT * FROM equipo_acceso WHERE telefono = ?",
            (telefono,),
        ).fetchone()
    return dict(row) if row else None


def marcar_esperando_clave_equipo(telefono: str) -> None:
    ahora = _utcnow().isoformat()
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO equipo_acceso (telefono, sesion_activa, esperando_clave, actualizado_at)
            VALUES (?, 0, 1, ?)
            ON CONFLICT(telefono) DO UPDATE SET
                esperando_clave = 1,
                sesion_activa = 0,
                expira_at = NULL,
                actualizado_at = excluded.actualizado_at
            """,
            (telefono, ahora),
        )


def cancelar_esperando_clave_equipo(telefono: str) -> None:
    with _transaction() as conn:
        conn.execute(
            """
            UPDATE equipo_acceso
            SET esperando_clave = 0, actualizado_at = ?
            WHERE telefono = ?
            """,
            (_utcnow().isoformat(), telefono),
        )


def esperando_clave_equipo(telefono: str) -> bool:
    fila = _fila_equipo_acceso(telefono)
    return bool(fila and fila.get("esperando_clave"))


def activar_sesion_equipo(telefono: str, nombre_miembro: str, horas: int) -> None:
    ahora = _utcnow()
    expira = (ahora + timedelta(hours=horas)).isoformat()
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO equipo_acceso (
                telefono, sesion_activa, esperando_clave, nombre_miembro, expira_at, actualizado_at
            ) VALUES (?, 1, 0, ?, ?, ?)
            ON CONFLICT(telefono) DO UPDATE SET
                sesion_activa = 1,
                esperando_clave = 0,
                nombre_miembro = excluded.nombre_miembro,
                expira_at = excluded.expira_at,
                actualizado_at = excluded.actualizado_at
            """,
            (telefono, nombre_miembro, expira, ahora.isoformat()),
        )


def cerrar_sesion_equipo(telefono: str) -> None:
    with _transaction() as conn:
        conn.execute(
            """
            UPDATE equipo_acceso
            SET sesion_activa = 0, esperando_clave = 0, expira_at = NULL, actualizado_at = ?
            WHERE telefono = ?
            """,
            (_utcnow().isoformat(), telefono),
        )


def sesion_equipo_activa(telefono: str) -> bool:
    fila = _fila_equipo_acceso(telefono)
    if not fila or not fila.get("sesion_activa"):
        return False
    expira_at = fila.get("expira_at")
    if not expira_at:
        return True
    try:
        expira = datetime.fromisoformat(expira_at)
    except ValueError:
        cerrar_sesion_equipo(telefono)
        return False
    if _utcnow() >= expira:
        cerrar_sesion_equipo(telefono)
        return False
    return True


def obtener_nombre_equipo_sesion(telefono: str) -> str:
    fila = _fila_equipo_acceso(telefono)
    if fila and fila.get("nombre_miembro"):
        return str(fila["nombre_miembro"])
    return "Equipo Inpulso"


def guardar_escalacion_local(telefono: str, nombre: str, motivo: str) -> int:
    with _transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO escalaciones_local (telefono, nombre, motivo, estado, notificado, creado_at)
            VALUES (?, ?, ?, 'PENDIENTE', 0, ?)
            """,
            (telefono, nombre or "", motivo, _utcnow().isoformat()),
        )
        return int(cur.lastrowid)


def marcar_escalacion_notificada(telefono: str) -> None:
    with _transaction() as conn:
        conn.execute(
            """
            UPDATE escalaciones_local
            SET notificado = 1
            WHERE id = (
                SELECT id FROM escalaciones_local
                WHERE telefono = ? AND estado = 'PENDIENTE'
                ORDER BY id DESC LIMIT 1
            )
            """,
            (telefono,),
        )


def contar_escalaciones_pendientes_local() -> int:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM escalaciones_local WHERE estado = 'PENDIENTE'"
        ).fetchone()
        return int(row["n"]) if row else 0


def resumen_metricas_operativas() -> dict:
    with _transaction() as conn:
        cola = conn.execute(
            "SELECT COUNT(*) AS n FROM cola_mensajes WHERE estado = 'pendiente'"
        ).fetchone()
        esc = conn.execute(
            "SELECT COUNT(*) AS n FROM escalaciones_local WHERE estado = 'PENDIENTE'"
        ).fetchone()
        conv = conn.execute(
            "SELECT COUNT(DISTINCT clave) AS n FROM conversacion_mensajes"
        ).fetchone()
    return {
        "cola_pendiente": int(cola["n"]) if cola else 0,
        "escalaciones_pendientes": int(esc["n"]) if esc else 0,
        "conversaciones_activas": int(conv["n"]) if conv else 0,
        "recepcion_configurada": bool(config.RECEPCION_WHATSAPP),
    }


def registrar_intento_clave_equipo_fallido(telefono: str) -> int:
    ahora = _utcnow()
    with _transaction() as conn:
        row = conn.execute(
            "SELECT fallos FROM equipo_clave_intentos WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        fallos = int(row["fallos"]) + 1 if row else 1
        conn.execute(
            """
            INSERT INTO equipo_clave_intentos (telefono, fallos, bloqueado_hasta, actualizado_at)
            VALUES (?, ?, NULL, ?)
            ON CONFLICT(telefono) DO UPDATE SET
                fallos = excluded.fallos,
                actualizado_at = excluded.actualizado_at
            """,
            (telefono, fallos, ahora.isoformat()),
        )
        return fallos


def resetear_intentos_clave_equipo(telefono: str) -> None:
    with _transaction() as conn:
        conn.execute(
            """
            INSERT INTO equipo_clave_intentos (telefono, fallos, bloqueado_hasta, actualizado_at)
            VALUES (?, 0, NULL, ?)
            ON CONFLICT(telefono) DO UPDATE SET
                fallos = 0,
                bloqueado_hasta = NULL,
                actualizado_at = excluded.actualizado_at
            """,
            (telefono, _utcnow().isoformat()),
        )


def equipo_clave_bloqueada(telefono: str, max_fallos: int, minutos_bloqueo: int) -> bool:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT fallos, bloqueado_hasta FROM equipo_clave_intentos WHERE telefono = ?",
            (telefono,),
        ).fetchone()
    if not row:
        return False
    if row["bloqueado_hasta"]:
        try:
            hasta = datetime.fromisoformat(row["bloqueado_hasta"])
            if _utcnow() < hasta:
                return True
        except ValueError:
            pass
    fallos = int(row["fallos"] or 0)
    if fallos < max_fallos:
        return False
    hasta = _utcnow() + timedelta(minutes=minutos_bloqueo)
    with _transaction() as conn:
        conn.execute(
            """
            UPDATE equipo_clave_intentos
            SET bloqueado_hasta = ?, fallos = 0, actualizado_at = ?
            WHERE telefono = ?
            """,
            (hasta.isoformat(), _utcnow().isoformat(), telefono),
        )
    return True
