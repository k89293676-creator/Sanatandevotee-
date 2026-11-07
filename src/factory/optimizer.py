"""Optimizer: Thompson sampling over arms, weights push."""
from __future__ import annotations
import json, random, math
from typing import Dict, List
from .db import connect, init_db
from .config import load_config
from .logging_setup import setup_logging

log = setup_logging("optimizer")
cfg = load_config()


def ensure_arms():
    init_db()
    conn = connect()
    cfgl = cfg
    types = cfgl.get("arm_types", ["hook_style","format","slot","visual_style","voice"])
    keys_map = {
        "hook_style": cfgl.get("hook_styles", []),
        "format": cfgl.get("formats", []),
        "visual_style": cfgl.get("visual_styles", []),
        "voice": cfgl.get("voices", []),
        "slot": cfgl["posting"]["start_slots_ist"] + cfgl["posting"].get("explore_slots_ist", []),
    }
    for at in types:
        for k in keys_map.get(at, []):
            conn.execute("INSERT OR IGNORE INTO arms (arm_type,arm_key) VALUES (?,?)", (at, k))
    conn.commit()
    conn.close()


def thompson_sample(arm_type: str) -> str:
    init_db()
    conn = connect()
    rows = conn.execute("SELECT arm_key,alpha,beta FROM arms WHERE arm_type=?", (arm_type,)).fetchall()
    conn.close()
    best = None
    best_val = -1
    for r in rows:
        a = r["alpha"]; b = r["beta"]
        # sample from Beta(a,b)
        import random
        x = random.betavariate(a, b)
        if x > best_val:
            best_val = x
            best = r["arm_key"]
    return best or (rows[0]["arm_key"] if rows else "")


def update_arm(arm_type: str, arm_key: str, reward: float):
    init_db()
    conn = connect()
    row = conn.execute("SELECT alpha,beta,n FROM arms WHERE arm_type=? AND arm_key=?", (arm_type, arm_key)).fetchone()
    if not row:
        conn.execute("INSERT INTO arms (arm_type,arm_key,alpha,beta,n) VALUES (?,?,1,1,0)", (arm_type, arm_key))
        row = {"alpha": 1, "beta": 1, "n": 0}
    # Beta update: reward in [0,1]
    a = row["alpha"] + reward
    b = row["beta"] + (1 - reward)
    conn.execute("UPDATE arms SET alpha=?,beta=?,n=n+1,last_update=datetime('now') WHERE arm_type=? AND arm_key=?",
                 (a, b, arm_type, arm_key))
    conn.commit()
    conn.close()


def weights() -> dict:
    ensure_arms()
    init_db()
    conn = connect()
    out = {}
    for (at,) in conn.execute("SELECT DISTINCT arm_type FROM arms").fetchall():
        rows = conn.execute("SELECT arm_key,alpha,beta,n FROM arms WHERE arm_type=?", (at,)).fetchall()
        tot_n = sum(r["n"] for r in rows) or 1
        out[at] = {r["arm_key"]: (r["alpha"] / (r["alpha"] + r["beta"])) for r in rows}
    conn.close()
    return out


def run_optimizer() -> dict:
    # placeholder: compute weights and store in kv
    ensure_arms()
    w = weights()
    init_db()
    conn = connect()
    conn.execute("INSERT OR REPLACE INTO kv (key,value,updated_at) VALUES (?,?,datetime('now'))",
                 ("weights", json.dumps(w)))
    conn.commit()
    conn.close()
    return {"weights": w}