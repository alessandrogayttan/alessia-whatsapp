import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import config

_lock = threading.Lock()


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
            (mensaje_id, datetime.utcnow().isoformat()),
        )
        if cur.rowcount == 0:
            return False
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
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
            (event_id, tipo, datetime.utcnow().isoformat()),
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
            (telefono, lat, lng, datetime.utcnow().isoformat()),
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
            (telefono, datetime.utcnow().isoformat()),
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
            (telefono, cita_clave, datetime.utcnow().isoformat()),
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
            (telefono, nombre, datetime.utcnow().isoformat()),
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
            (codigo.upper(), telefono_nuevo, datetime.utcnow().isoformat()),
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
            (telefono, event_id, escala, notas, datetime.utcnow().isoformat()),
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
    mes = datetime.utcnow().strftime("%Y-%m")
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
            (telefono, event_id, datetime.utcnow().isoformat()),
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
                datetime.utcnow().isoformat(),
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
            (telefono, event_id, datetime.utcnow().isoformat()),
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
            (telefono, event_id, datetime.utcnow().isoformat()),
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
            (telefono, puntaje, event_id, datetime.utcnow().isoformat()),
        )
        conn.execute("DELETE FROM nps_pendiente WHERE telefono = ?", (telefono,))


def obtener_ultimo_nps(telefono: str) -> int | None:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT puntaje FROM nps_respuestas WHERE telefono = ?",
            (telefono,),
        ).fetchone()
        return row["puntaje"] if row else None


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
                datetime.utcnow().isoformat(),
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
            (telefono, event_id, datetime.utcnow().isoformat()),
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
            (telefono, event_id, nota, datetime.utcnow().isoformat()),
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
            (telefono, anio, datetime.utcnow().isoformat()),
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
            (clave, datetime.utcnow().isoformat()),
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
                datetime.utcnow().isoformat(),
            ),
        )
        return cur.lastrowid


def tareas_pendientes_hoy(dia_nombre: str) -> list[dict]:
    hoy = datetime.utcnow().strftime("%Y-%m-%d")
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
                datetime.utcnow().isoformat(),
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
            (clave, datetime.utcnow().isoformat()),
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
            (telefono, taller_clave, datetime.utcnow().isoformat()),
        )


def marcar_tarea_enviada_hoy(tarea_id: int, fecha: str):
    with _transaction() as conn:
        conn.execute(
            "UPDATE tareas_terapeuticas SET ultimo_envio = ? WHERE id = ?",
            (fecha, tarea_id),
        )


def encolar_mensaje_ia(telefono: str, contenido: str) -> int:
    ahora = datetime.utcnow().isoformat()
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
    ahora = datetime.utcnow().isoformat()
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
    ahora = datetime.utcnow().isoformat()
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
    ahora = datetime.utcnow().isoformat()
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
    ahora = datetime.utcnow().isoformat()
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
