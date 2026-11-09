import { Env, sb } from "./db";
import { now } from "./clock";
import { dedupeAlert } from "./alerts";

// Health checks for the Make.com path, run from scheduled():
//  - handed_off rows that were never acked trigger a reminder, then `unknown`
//  - a missing/stale make_last_call ping triggers a dead-man alert
// Alerts are deduped per reel / per day so cron cannot spam Telegram.

function intEnv(value: string | undefined, def: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : def;
}

export interface MakeHealth {
  unacked: number;
  dead: boolean;
}

async function readState(env: Env, key: string): Promise<any> {
  const r = await sb(env, `/relay_state?key=eq.${encodeURIComponent(key)}&select=value`);
  const rows = r.ok ? ((await r.json()) as any[]) : [];
  return rows.length ? rows[0].value : null;
}

export async function checkMakeHealth(env: Env): Promise<MakeHealth> {
  const unackedMin = intEnv(env.MAKE_UNACKED_ALERT_MINUTES, 30);
  const deadMin = intEnv(env.MAKE_DEADMAN_MINUTES, 75);

  let unacked = 0;
  const q = await sb(env, "/relay_queue?status=eq.handed_off&ack_status=is.null&select=id,handed_off_at");
  const rows = q.ok ? ((await q.json()) as any[]) : [];
  for (const row of rows) {
    const ts = row.handed_off_at ? new Date(row.handed_off_at).getTime() : NaN;
    const ageMin = Number.isNaN(ts) ? Infinity : (Date.now() - ts) / 60000;
    if (ageMin > deadMin) {
      await sb(env, `/relay_queue?id=eq.${row.id}&status=eq.handed_off`, {
        method: "PATCH",
        body: JSON.stringify({
          status: "unknown",
          ack_status: "timeout",
          last_error: `no ack after ${Math.round(ageMin)} min`,
        }),
      });
      await dedupeAlert(
        env,
        `make_unknown:${row.id}`,
        `Reel ${row.id} was handed to Make but never acked; marked unknown.`,
      );
    } else if (ageMin > unackedMin) {
      unacked += 1;
      await dedupeAlert(
        env,
        `make_unacked:${row.id}`,
        `Reel ${row.id} handed to Make ${Math.round(ageMin)} min ago and still not acked.`,
      );
    }
  }

  const last = await readState(env, "make_last_call");
  const ts = last && last.ts ? new Date(last.ts).getTime() : NaN;
  const dead = Number.isNaN(ts) || (Date.now() - ts) / 60000 > deadMin;
  if (dead) {
    const day = now().toISOString().slice(0, 10);
    await dedupeAlert(
      env,
      `make_deadman:${day}`,
      "Make has not called the relay within the dead-man window. Check the scenario and the laptop.",
    );
  }

  return { unacked, dead };
}
