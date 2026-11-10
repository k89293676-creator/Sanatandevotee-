"""Factory daemon: autostart entrypoint."""
from __future__ import annotations
import os, sys, time, socket, atexit, json, threading
from pathlib import Path
from .config import project_root, load_config
from .db import init_db, connect
from .logging_setup import setup_logging
from .power import can_render, max_threads
from .verses import upsert_verses, load_pack
from . import optimizer, planner, sync, cleanup, jobs

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

_HEAVY_LOCK = threading.Lock()

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
    delay = 2
    while time.time() < deadline:
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            return True
        except Exception:
            time.sleep(min(delay, 30))
            delay = min(delay * 2, 30)
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
    # run scriptgen if keys present.
    # Generating the whole missing corpus is bulk LLM work and can take 30+ min on
    # the Groq free tier, which would block the daemon from ever reaching tick().
    # So it only runs during an explicit heavy pass; otherwise we just top up the
    # handful of scripts the planner needs with ensure_min_scripts.
    if os.environ.get("ALLOW_HEAVY") == "1":
        try:
            from . import scriptgen
            r = scriptgen.run("shiv_chalisa", resume=True)
            log.info("scriptgen %s", r)
        except Exception as e:
            log.error("scriptgen err %s", e)
    else:
        try:
            from . import script_store
            r = script_store.ensure_min_scripts(3)
            log.info("scriptgen skipped (set ALLOW_HEAVY=1 for the full corpus); ensure_min_scripts=%s", r)
        except Exception as e:
            log.error("ensure_min_scripts err %s", e)
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


def resubmit_pending_approval(relay_url: str) -> int:
    """Ensure every locally pending reel has a public preview in the dashboard queue."""
    if not relay_url:
        return 0
    fixed = 0
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM reels WHERE status='pending_approval' "
            "AND (remote_video_url IS NULL OR remote_video_url='')").fetchall()
    finally:
        conn.close()
    for r in rows:
        row = dict(r)
        script = None
        try:
            c2 = connect()
            sc = c2.execute("SELECT * FROM scripts WHERE id=?", (row.get("script_id"),)).fetchone()
            c2.close()
            script = dict(sc) if sc else None
        except Exception:
            script = None
        if jobs.submit_for_approval(row, script, relay_url):
            fixed += 1
        else:
            # unrenderable legacy rows should go back to the plan instead of blocking the queue
            if jobs._reel_video_path(row) is None:
                conn2 = connect()
                try:
                    jobs._mark(conn2, row["uuid"], status="planned", last_error="no rendered file")
                finally:
                    conn2.close()
    return fixed


def tick(relay_url: str):
    # Connectivity gate: do not attempt jobs without network.
    if not wait_network(1):
        log.warning("tick: no network; skipping heavy jobs")
        return
    sync.heartbeat(relay_url)
    st = sync.get_state(relay_url)
    if st:
        log.info("buffer_days=%s", st.get("buffer_days"))
    # content job: ensure script bank (only for verified units)
    try:
        from . import content_engine, script_store, verses
        vs = verses.get_verses("shiv_chalisa")
        verified = [v for v in vs if v.get("verified_flag") == 1]
        # maintain a minimum of 5 planned scripts in the bank
        try:
            script_store.ensure_min_scripts(5)
        except Exception as e:
            log.warning("ensure_min_scripts err %s", e)
        with _HEAVY_LOCK:
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
    # H2 round-trip: dashboard approvals -> local approved buffer (`rendered`)
    try:
        n = jobs.sync_approved_reels(relay_url)
        if n:
            log.info("synced %d approved reels", n)
    except Exception as e:
        log.warning("sync_approved err %s", e)
    # make sure every pending reel really has a public preview in the queue
    try:
        fixed = resubmit_pending_approval(relay_url)
        if fixed:
            log.info("re-submitted %d reels for approval", fixed)
    except Exception as e:
        log.warning("resubmit_pending err %s", e)
    # render one planned reel per tick, then queue it for human approval (H2)
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
        with _HEAVY_LOCK:
            try:
                jobs.render_reel_row(r)
            except Exception as e:
                log.error("render failed %s: %s", r["uuid"], e)
                jobs.mark_failed(r, str(e))
                break
            try:
                c2 = connect()
                sc = c2.execute("SELECT * FROM scripts WHERE id=?", (r["script_id"],)).fetchone()
                c2.close()
                script = dict(sc) if sc else None
                if not jobs.submit_for_approval(dict(r), script, relay_url):
                    log.warning("reel %s rendered but not queued for approval", r["uuid"])
            except Exception as e:
                log.warning("submit_for_approval failed %s: %s", r["uuid"], e)
            break
    # refill plan
    try:
        planner.plan("shiv_chalisa", days=CFG["scheduling"]["buffer_target_days"])
    except Exception as e:
        log.error("plan err %s", e)
    # unbreakable content buffer: top off to 5 pre-rendered reels
    try:
        jobs.ensure_buffer_floor(5, relay_url)
    except Exception as e:
        log.warning("ensure_buffer_floor err %s", e)
    # strategy tick: Groq-driven analytics optimization
    try:
        from . import strategy
        res = strategy.strategy_tick()
        log.info("strategy tick %s", res)
        # push strategy outputs to relay_state via the relay worker (no Supabase creds on laptop)
        try:
            from . import strategy as _st
            payload = {}
            if _st.REPORT_PATH.exists():
                payload["weekly_report"] = _st.REPORT_PATH.read_text(encoding="utf-8")[:4000]
            notes_path = _st.ROOT / "data" / "prompt_notes.md"
            if notes_path.exists():
                payload["prompt_notes"] = notes_path.read_text(encoding="utf-8")[:4000]
            if payload:
                jobs.push_state(relay_url, payload)
        except Exception as e:
            log.warning("strategy push err %s", e)
    except Exception as e:
        log.warning("strategy tick err %s", e)
    # lessons memo: periodically ingest optimizer summary into prompt_notes.md
    try:
        from . import lessons_memo, optimizer
        summary = json.dumps(optimizer.run_optimizer(), ensure_ascii=False)[:4000]
        lessons_memo.generate_lessons_memo(summary)
        # self-adjust: read memo if present and log (soft guidance only)
        notes_path = lessons_memo.NOTES_PATH
        if notes_path.exists():
            log.info("lessons memo present (%d bytes)", notes_path.stat().st_size)
    except Exception as e:
        log.warning("lessons_memo err %s", e)
    # publish a local buffer snapshot so the dashboard shows real numbers
    try:
        snap = jobs.buffer_snapshot(relay_url, CFG["scheduling"].get("buffer_target_days", 5))
        log.info("buffer snapshot rendered=%s pending=%s planned=%s",
                 snap.get("rendered"), snap.get("pending_approval"), snap.get("planned"))
    except Exception as e:
        log.warning("buffer snapshot err %s", e)
    # live analytics: refresh YouTube stats where the OAuth creds actually live (laptop)
    try:
        from . import analytics as analytics_mod
        snap = analytics_mod.push_analytics(relay_url)
        log.info("analytics snapshot: %s videos, totals %s",
                 len(snap.get("items", [])), snap.get("totals"))
    except Exception as e:
        log.warning("analytics tick err %s", e)
    # disk hygiene
    try:
        cleanup.run_cleanup()
    except Exception as e:
        log.error("cleanup err %s", e)


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