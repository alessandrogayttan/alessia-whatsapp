"""Backup seguro de SQLite (API online backup, no copy2 a caliente)."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def backup_sqlite(src_path: str | Path, dest_path: str | Path) -> Path:
    """Copia consistente de la base usando sqlite3.Connection.backup."""
    src = Path(src_path)
    dest = Path(dest_path)
    if not src.is_file():
        raise FileNotFoundError(f"No existe la base: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(src), timeout=60)
    dest_conn = sqlite3.connect(str(dest))
    try:
        src_conn.backup(dest_conn)
        dest_conn.commit()
    finally:
        dest_conn.close()
        src_conn.close()
    logger.info("Backup SQLite: %s → %s", src, dest)
    return dest


def prune_backups(dest_dir: str | Path, pattern: str = "alessia_*.db", keep: int = 14) -> int:
    """Elimina backups viejos; devuelve cuántos borró."""
    folder = Path(dest_dir)
    if not folder.is_dir():
        return 0
    backups = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime)
    borrados = 0
    for viejo in backups[:-keep] if keep > 0 else backups:
        try:
            viejo.unlink(missing_ok=True)
            borrados += 1
        except OSError as e:
            logger.warning("No se pudo borrar backup %s: %s", viejo, e)
    return borrados
