"""Planner: schedule reels ahead."""
from __future__ import annotations
import uuid, json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from .config import load_config
from .db import connect, init_db
from .logging_setup import setup_logging

log = setup_logging("planner")
cfg = load_config()
TZ = "Asia/Kolkata"


def _ist_now() -> datetime:
    # store UTC; schedule in IST slots. We'll treat slots as IST wall times converted to UTC.
    import zoneinfo
    return datetime.now(timezone.utc).astimezone(zoneinfo.ZoneInfo("Asia/Kolkata"))


def ist_to_utc(dt_ist: datetime) -> datetime:
    import zoneinfo
    return dt_ist.replace(tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)


def special_days(years: int = 5) -> set:
    # Mondays, Pradosh (13th tithi approximated as 13th day of lunar half - we approximate with calendar 13th?),
    # Shravan Mondays, Maha Shivratri, Kartik Purnima. We'll compute Mondays + a few fixed dates simply.
    import zoneinfo
    res = set()
    now = datetime.now(timezone.utc).astimezone(zoneinfo.ZoneInfo("Asia/Kolkata"))
    for y in range(now.year, now.year + years):
        # Mondays
        d = datetime(y, 1, 1, tzinfo=zoneinfo.ZoneInfo("Asia/Kolkata"))
        while d.year == y:
            if d.weekday() == 0:
                res.add(d.date().isoformat())
            d += timedelta(days=1)
        # Maha Shivratri approx: Feb/Mar; use 26 Feb as placeholder? We'll add Feb 26
        res.add(f"{y}-02-26")
        # Kartik Purnima approx: Nov full moon; use Nov 15
        res.add(f"{y}-11-15")
    return res


def next_unseen_verse(conn, pack: str) -> dict | None:
    # verse not yet used as "first reel of day meaning" — we track via reels series_day? Simpler: pick lowest seq not yet in reels as meaning format.
    used = {r["verse_id"] for r in conn.execute("SELECT verse_id FROM reels WHERE format='meaning'").fetchall()}
    rows = conn.execute("SELECT * FROM verses WHERE pack=? ORDER BY seq", (pack,)).fetchall()
    for r in rows:
        if r["id"] not in used:
            return dict(r)
    return None


def plan(pack: str = "shiv_chalisa", days: int = None) -> dict:
    cfg = load_config()
    days = days or cfg["scheduling"]["buffer_target_days"]
    init_db()
    conn = connect()
    slots = cfg["posting"]["start_slots_ist"] + cfg["posting"].get("explore_slots_ist", [])
    reels_per_day = cfg["posting"]["reels_per_day"]
    min_gap = cfg["scheduling"]["min_gap_hours"]
    jitter = cfg["posting"]["jitter_minutes"]
    import random
    now_ist = _ist_now()
    # start from tomorrow 06:30
    cursor_date = now_ist.date()
    created = 0
    # determine already scheduled last date
    last = conn.execute("SELECT MAX(scheduled_at_utc) m FROM reels").fetchone()
    if last and last["m"]:
        last_dt = datetime.fromisoformat(last["m"].replace("Z", "+00:00"))
        cursor_date = last_dt.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata")).date() + timedelta(days=1)
    sd_set = special_days(5)
    # reserve pool: create reserve_reels evergreen reels unscheduled
    reserve_n = cfg["scheduling"]["reserve_reels"]
    existing_reserve = conn.execute("SELECT COUNT(*) c FROM reels WHERE is_reserve=1").fetchone()["c"]
    # create reserves if needed
    verses = [dict(r) for r in conn.execute("SELECT * FROM verses WHERE pack=? ORDER BY seq", (pack,)).fetchall()]
    scripts = { (s["verse_id"], s["format"]): dict(s) for s in conn.execute("SELECT * FROM scripts").fetchall() }
    # reserve: story/when formats, no day number
    ri = 0
    while existing_reserve + ri < reserve_n and ri < len(verses):
        v = verses[ri % len(verses)]
        for fmt in ["story", "when"]:
            if (v["id"], fmt) in scripts:
                if not conn.execute("SELECT 1 FROM reels WHERE verse_id=? AND format=? AND is_reserve=1", (v["id"], fmt)).fetchone():
                    uid = str(uuid.uuid4())
                    conn.execute(
                        """INSERT INTO reels (uuid,verse_id,script_id,format,hook_idx,hook_style,voice,visual_style,slot_label,series_day,is_reserve,status)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (uid, v["id"], scripts[(v["id"], fmt)]["id"], fmt, 0, "question", "madhur",
                         "cosmic_blue", "reserve", None, 1, "planned"),
                    )
                    ri += 1
                    existing_reserve += 1
                    if existing_reserve >= reserve_n:
                        break
        ri += 1
    conn.commit()

    day = 0
    while day < days:
        d = cursor_date + timedelta(days=day)
        is_special = d.isoformat() in sd_set
        day_slots = list(slots[:reels_per_day])
        if is_special:
            day_slots = day_slots + [slots[0]]  # extra
        # cap hard
        day_slots = day_slots[:cfg["posting"]["max_reels_per_day_hard_cap"]]
        # first reel = next unseen verse meaning (or recital weekly)
        first_done = False
        for si, slot in enumerate(day_slots):
            # pick format
            if si == 0:
                v = next_unseen_verse(conn, pack)
                if v is None:
                    # revisit: any verse
                    v = verses[day % len(verses)]
                fmt = "meaning"
                if d.weekday() == 6:  # Sunday recital
                    fmt = "recital"
                series_day = v["seq"]  # use seq as day number proxy
                # ensure script exists
                if (v["id"], fmt) not in scripts:
                    fmt = "meaning"
                if (v["id"], fmt) not in scripts:
                    continue
            else:
                # other formats of already-covered verses
                # pick a verse already used
                used_ids = [r["verse_id"] for r in conn.execute("SELECT verse_id FROM reels WHERE series_day IS NOT NULL").fetchall()]
                if not used_ids:
                    used_ids = [verses[0]["id"]]
                v = verses[(day + si) % len(verses)]
                # choose a format different
                fmt = ["story", "when", "meaning"][si % 3]
                if (v["id"], fmt) not in scripts:
                    fmt = "meaning"
                if (v["id"], fmt) not in scripts:
                    continue
                series_day = None
            # no repeat (verse,format) within 30 days
            recent = conn.execute(
                "SELECT 1 FROM reels WHERE verse_id=? AND format=? AND created_at > datetime('now','-30 days')",
                (v["id"], fmt)).fetchone()
            if recent:
                continue
            # build scheduled_at
            hh, mm = slot.split(":")
            base = datetime(d.year, d.month, d.day, int(hh), int(mm), tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
            import random
            j = random.randint(-jitter, jitter)
            base = base + timedelta(minutes=j)
            utc = base.astimezone(timezone.utc)
            # min gap check: ensure not too close to previous reel
            prev = conn.execute("SELECT scheduled_at_utc FROM reels ORDER BY scheduled_at_utc DESC LIMIT 1").fetchone()
            if prev and prev["scheduled_at_utc"]:
                prev_dt = datetime.fromisoformat(prev["scheduled_at_utc"].replace("Z", "+00:00"))
                if (utc - prev_dt).total_seconds() < min_gap * 3600:
                    utc = prev_dt + timedelta(hours=min_gap)
            uid = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO reels (uuid,verse_id,script_id,format,hook_idx,hook_style,voice,visual_style,slot_label,series_day,is_reserve,scheduled_at_utc,status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (uid, v["id"], scripts[(v["id"], fmt)]["id"], fmt, 0, "question",
                 "madhur", "cosmic_blue", slot, series_day, 0, utc.isoformat(), "planned"),
            )
            created += 1
        day += 1
    conn.commit()
    conn.close()
    return {"created": created, "days": days}