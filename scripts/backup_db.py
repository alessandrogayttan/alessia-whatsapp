"""Copia de seguridad de alessia.db (ejecutar local o en cron)."""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from db_backup import backup_sqlite, prune_backups  # noqa: E402


def main():
    src = Path(config.DATABASE_PATH)
    if not src.is_file():
        print(f"No existe la base de datos: {src}")
        sys.exit(1)
    dest_dir = Path(config.BACKUP_DIR)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"alessia_{stamp}.db"
    backup_sqlite(src, dest)
    prune_backups(dest_dir, keep=14)
    print(f"Backup creado: {dest}")


if __name__ == "__main__":
    main()
