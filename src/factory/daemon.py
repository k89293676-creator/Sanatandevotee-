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


import msvcrt

def acquire_lock() -> bool:
    try:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        f = open(LOCK, "w")
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            f.close()
            return False
        f.write(str(os.getpid()))
        f.flush()
        # keep handle open for lifetime
        _LOCK_HANDLE.append(f)
        return True
    except Exception as e:
        log.error("lock err %s", e)
        return False

_LOCK_HANDLE = []

def release_lock():
    for f in _LOCK_HANDLE:
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            f.close()
        except Exception:
            pass
    try:
        if LOCK.exists():
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
    sync.heartbeat(relay_url)
    st = sync.get_state(relay_url)
    if st:
        log.info("buffer_days=%s", st.get("buffer_days"))
    # content job: ensure script bank (only for verified units)
    try:
        from . import content_engine, script_store, verses
        vs = verses.get_verses("shiv_chalisa")
        verified = [v for v in vs if v.get("verified_flag") == 1]
        for v in verified[:1]:  # one per tick
            for fmt in ["meaning", "recital"]:
                try:
                    s = content_engine.generate_script(v, fmt)
                    if s:
                        sid = script_store.save_script(v, fmt, s)
                        log.info("generated script %s/%s -> id %s (score %s)", v["id"], fmt, sid,
                                 (s.get("score") or {}).get("total"))
                except Exception as e:
                    log.error("gen err %s", e)
    except Exception as e:
        log.error("content_job err %s", e)
    # render the earliest due planned reel, then upload it to the relay
    from .db import connect
    from . import jobs
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM reels WHERE status='planned' AND scheduled_at_utc IS NOT NULL "
        "ORDER BY scheduled_at_utc LIMIT 1").fetchall()
    conn.close()
    for r in rows:
        if not can_render():
            log.info("skip render: power policy")
            break
        log.info("rendering reel %s", r["uuid"])
        try:
            man = jobs.render_reel_row(r)
        except Exception as e:
            log.error("render failed %s: %s", r["uuid"], e)
            jobs.mark_failed(r, str(e))
            break
        if CFG.get("scheduling", {}).get("mode", "cloud_relay") == "cloud_relay":
            try:
                jobs.upload_reel(r, man, relay_url)
            except Exception as e:
                log.error("upload failed %s: %s", r["uuid"], e)
        break
    # refill plan
    try:
        planner.plan("shiv_chalisa", days=CFG["scheduling"]["buffer_target_days"])
    except Exception as e:
        log.error("plan err %s", e)
    # run optimizer
    try:
        optimizer.run_optimizer()
    except Exception as e:
        log.error("optimizer err %s", e)


def main():
    if not acquire_lock():
        log.error("another daemon running")
        sys.exit(1)
    atexit.register(release_lock)
    wait_network(CFG["laptop"].get("network_wait_minutes", 10))
    import yaml
    cfg = yaml.safe_load(open(ROOT / "config" / "config.yaml", encoding="utf-8"))
    relay_url = os.environ.get("RELAY_URL", cfg.get("relay", {}).get("url", "https://chalisa-relay.mew92724.workers.dev"))
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