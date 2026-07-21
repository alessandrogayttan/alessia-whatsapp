"""Backup seguro de SQLite + subida opcional a Spaces/S3."""
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


def subir_backup_offsite(local_path: str | Path) -> bool:
    """
    Sube a DigitalOcean Spaces / S3 si BACKUP_S3_* está configurado.
    No falla el backup local si la subida falla.
    """
    import config

    path = Path(local_path)
    if not path.is_file():
        return False
    if not (
        config.BACKUP_S3_ENDPOINT
        and config.BACKUP_S3_BUCKET
        and config.BACKUP_S3_ACCESS_KEY
        and config.BACKUP_S3_SECRET_KEY
    ):
        return False
    try:
        import boto3
        from botocore.client import Config as BotoConfig

        client = boto3.client(
            "s3",
            endpoint_url=config.BACKUP_S3_ENDPOINT,
            aws_access_key_id=config.BACKUP_S3_ACCESS_KEY,
            aws_secret_access_key=config.BACKUP_S3_SECRET_KEY,
            region_name=config.BACKUP_S3_REGION or "nyc3",
            config=BotoConfig(signature_version="s3v4"),
        )
        key = f"alessia-backups/{path.name}"
        client.upload_file(str(path), config.BACKUP_S3_BUCKET, key)
        logger.info("Backup offsite subido: s3://%s/%s", config.BACKUP_S3_BUCKET, key)
        return True
    except ImportError:
        logger.warning("boto3 no instalado: omitiendo backup offsite")
        return False
    except Exception as e:
        logger.error("Fallo backup offsite: %s", e)
        return False
