"""Deploydan keyin SQLite yo'qolmasin — volume, migratsiya, startup zaxira."""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
TZ = ZoneInfo(os.getenv("TZ", "Asia/Tashkent"))
DEFAULT_DATA_DIR = "/data"
_STARTUP_BACKUP_KEEP = max(5, int(os.getenv("STARTUP_BACKUP_KEEP", "30")))


def resolve_db_path(*, env_key: str = "DB_PATH", default_filename: str = "martekovka.db") -> str:
    raw = (os.getenv(env_key, "") or "").strip()
    if raw:
        return raw
    mount = (os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "") or "").strip()
    if mount:
        return os.path.join(mount, default_filename)
    return os.path.join(DEFAULT_DATA_DIR, default_filename)


def ensure_data_dir(db_path: str) -> str:
    directory = os.path.dirname(os.path.abspath(db_path)) or "."
    os.makedirs(directory, exist_ok=True)
    return directory


def has_railway_volume() -> bool:
    return bool((os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "") or "").strip())


def migrate_legacy_db(target_path: str, *extra_legacy: str) -> str | None:
    target = os.path.abspath(target_path)
    if os.path.isfile(target) and os.path.getsize(target) > 512:
        return None
    base = os.path.basename(target)
    candidates: list[str] = []
    for p in (*extra_legacy, base, os.path.join("/app", base)):
        if p and p not in candidates:
            candidates.append(p)
    for src in candidates:
        src_abs = src if os.path.isabs(src) else os.path.abspath(src)
        if src_abs == target or not os.path.isfile(src_abs):
            continue
        try:
            if os.path.getsize(src_abs) < 1:
                continue
            ensure_data_dir(target)
            shutil.copy2(src_abs, target)
            log.warning("DB migratsiya: %s -> %s", src_abs, target)
            return src_abs
        except OSError as exc:
            log.warning("DB migratsiya xato %s: %s", src_abs, exc)
    return None


def startup_sqlite_backup(db_path: str) -> str | None:
    if not os.path.isfile(db_path):
        return None
    out = os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")
    os.makedirs(out, exist_ok=True)
    stamp = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(out, f"startup_{stamp}.db")
    try:
        shutil.copy2(db_path, dest)
        log.info("Startup zaxira: %s", dest)
        return dest
    except OSError as exc:
        log.error("Startup zaxira xato: %s", exc)
        return None


def bootstrap_persistence(db_path: str, *, legacy_names: tuple[str, ...] = ("martekovka.db",)) -> dict:
    path = os.path.abspath(db_path)
    ensure_data_dir(path)
    migrated_from = migrate_legacy_db(path, *legacy_names)
    backup_file = startup_sqlite_backup(path)
    volume = has_railway_volume()
    if not volume and path.startswith("/data"):
        log.critical("RAILWAY VOLUME YO'Q — /data deploydan keyin o'chadi!")
    return {"db_path": path, "volume": volume, "migrated_from": migrated_from, "startup_backup": backup_file}


def persistence_status_line(db_path: str) -> str:
    vol = has_railway_volume()
    mount = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "") or "—"
    size = os.path.getsize(db_path) if os.path.isfile(db_path) else 0
    return f"DB: {db_path} ({size // 1024} KB) · Volume: {'✅' if vol else '❌'} ({mount})"
