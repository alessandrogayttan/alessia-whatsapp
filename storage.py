import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta

import config

_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(config.DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


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
