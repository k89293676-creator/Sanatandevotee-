"""Factory daemon: autostart entrypoint."""
from __future__ import annotations
import os, sys, time, socket, atexit
from pathlib import Path
from .config import project_root, load_config
from .db import init_db
from .logging_setup import setup_logging
from .power import can_render, max_threads
from .verses import upsert_verses, load_pack
from . import optimizer, planner, sync

log = setup_logging("daemon")
ROOT = project_root()
LOCK = ROOT / "data" / "daemon.lock"
CFG = load_config()


def acquire_lock() -> bool:
    try:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        if LOCK.exists():
            # check if process alive
            try:
                pid = int(LOCK.read_text().strip())
                # windows: check via tasklist? simple: try open
                os.kill(pid, 0)
                return False
            except Exception:
                pass
        LOCK.write_text(str(os.getpid()))
        return True
    except Exception as e:
        log.error("lock err %s", e)
        return False


def release_lock():
    try:
        if LOCK.exists() and LOCK.read_text().strip() == str(os.getpid()):
            LOCK.unlink()
    except Exception:
        pass


def wait_network(minutes: int = 10):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            return True
        except Exception:
            time.sleep(5)
    return False


def catch_up(relay_url: str):
    log.info("catch-up start")
    # load verses
    try:
        vs = load_pack("shiv_chalisa")
        # need id assignment; upsert
        # attach pack field already
        # ensure id not in json; db autoincrement
        # We'll upsert; ids assigned by db
        upsert_verses("shiv_chalisa", vs)
    except Exception as e:
        log.error("verses load err %s", e)
    # run scriptgen if keys present
    try:
        from . import scriptgen
        r = scriptgen.run("shiv_chalisa", resume=True)
        log.info("scriptgen %s", r)
    except Exception as e:
        log.error("scriptgen err %s", e)
    # plan to buffer
    try:
        planner.plan("shiv_chalisa", days=CFG["scheduling"]["buffer_target_days"])
    except Exception as e:
        log.error("planner err %s", e)
    # optimizer
    try:
        optimizer.run_optimizer()
    except Exception as e:
        log.error("optimizer err %s", e)


def tick(relay_url: str):
    # heartbeat
    sync.heartbeat(relay_url)
    # state
    st = sync.get_state(relay_url)
    if st:
        log.info("buffer_days=%s", st.get("buffer_days"))
    # render earliest gaps: find planned reels without video_path, render+upload
    from .db import connect
    conn = connect()
    rows = conn.execute("SELECT * FROM reels WHERE status='planned' AND video_path IS NULL ORDER BY scheduled_at_utc LIMIT 1").fetchall()
    conn.close()
    for r in rows:
        if not can_render():
            log.info("skip render: power policy")
            break
        # render (simplified: skip if no script)
        log.info("would render reel %s", r["uuid"])
    # top-up planning handled in catch_up; periodic re-plan
    time.sleep(1)


def main():
    if not acquire_lock():
        log.error("another daemon running")
        sys.exit(1)
    atexit.register(release_lock)
    wait_network(CFG["laptop"].get("network_wait_minutes", 10))
    relay_url = os.environ.get("RELAY_URL", "http://localhost:8787")
    catch_up(relay_url)
    tick_minutes = CFG["laptop"].get("tick_minutes", 15)
    while True:
        try:
            tick(relay_url)
        except Exception as e:
            log.error("tick err %s", e)
        time.sleep(tick_minutes * 60)


if __name__ == "__main__":
    main()