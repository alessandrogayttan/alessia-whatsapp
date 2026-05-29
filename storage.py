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
