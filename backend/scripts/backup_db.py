#!/usr/bin/env python3
"""Daily SQLite backup with rotation. Run by politrain-backup.timer (systemd user unit).

Uses the sqlite3 online backup API — safe to run while uvicorn is writing.
Verifies integrity of the copy, gzips it into ~/backups/, keeps the newest KEEP files.
Stdlib only — runs on system python3, no venv needed.
"""
import gzip
import shutil
import sqlite3
import sys
import time
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "politrain.db"
BACKUP_DIR = Path.home() / "backups"
KEEP = 14


def main():
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tmp = BACKUP_DIR / f"politrain-{stamp}.db"

    src = sqlite3.connect(str(DB))
    dst = sqlite3.connect(str(tmp))
    with dst:
        src.backup(dst)
    src.close()

    check = dst.execute("PRAGMA integrity_check").fetchone()[0]
    dst.close()
    if check != "ok":
        tmp.unlink(missing_ok=True)
        print(f"BACKUP FAILED: integrity_check = {check}", file=sys.stderr)
        sys.exit(1)

    gz = BACKUP_DIR / f"politrain-{stamp}.db.gz"
    with open(tmp, "rb") as fin, gzip.open(gz, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    tmp.unlink()

    backups = sorted(BACKUP_DIR.glob("politrain-*.db.gz"))
    for old in backups[:-KEEP]:
        old.unlink()

    print(f"backup ok: {gz.name} ({gz.stat().st_size // 1024} KB), kept {min(len(backups), KEEP)}")


if __name__ == "__main__":
    main()
