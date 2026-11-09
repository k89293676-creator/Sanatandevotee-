"""Disk hygiene: purge intermediate work dirs and old cached media."""
from __future__ import annotations
import shutil, time
from pathlib import Path
from .config import media_dir, load_config
from .logging_setup import setup_logging

log = setup_logging("cleanup")
WORK = media_dir() / "work"
RENDERS = media_dir() / "renders"


def cleanup_work_dir(uuid: str) -> None:
    d = WORK / uuid
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def purge_old_mp4s(max_age_hours: int = 48) -> int:
    if not RENDERS.exists():
        return 0
    cutoff = time.time() - max_age_hours * 3600
    n = 0
    for p in RENDERS.glob("*.mp4"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
                n += 1
        except Exception as e:
            log.warning("purge err %s", e)
    return n


def enforce_disk_budget(min_free_gb: float = 2.0) -> None:
    import shutil as sh
    try:
        free = sh.disk_usage(media_dir()).free / (1024 ** 3)
    except Exception:
        return
    if free < min_free_gb:
        # purge oldest mp4s until budget met
        files = sorted(RENDERS.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        for p in files:
            try:
                p.unlink(missing_ok=True)
                free = sh.disk_usage(media_dir()).free / (1024 ** 3)
                if free >= min_free_gb:
                    break
            except Exception as e:
                log.warning("budget purge err %s", e)


def run_cleanup() -> None:
    purge_old_mp4s(48)
    enforce_disk_budget(2.0)
    log.info("cleanup done")