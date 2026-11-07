import { Env } from "./db";
import { now, setClock, realClock } from "./clock";
import { stepPublisher } from "./publisher";
import { stepEngage } from "./engage";
import { stepYoutube } from "./youtube";
import { telegram, dedupeAlert } from "./alerts";
import { sb } from "./db";

export async function scheduled(env: Env, event: ScheduledEvent): Promise<void> {
  const start = Date.now();
  // 1. heartbeat
  await sb(env, "/relay_state", {
    method: "POST",
    headers: { "Prefer": "resolution=merge-duplicates" },
    body: JSON.stringify({ key: "relay_last_run", value: { ts: now().toISOString() } }),
  });
  // 2. token refresh
  // (handled in publisher)
  // 3. publisher.step
  try { await stepPublisher(env); } catch (e) { await telegram(env, "Publisher error: " + String(e)); }
  // 4. youtube.step
  try { await stepYoutube(env); } catch (e) { await telegram(env, "YouTube error: " + String(e)); }
  // 5. engage.step every poll_every_minutes (throttle via kv cursor)
  const lastEngage = await env.TOKENS.get("last_engage");
  const nowMs = Date.now();
  if (!lastEngage || nowMs - Number(lastEngage) > 5 * 60 * 1000) {
    try { await stepEngage(env); } catch (e) { await telegram(env, "Engage error: " + String(e)); }
    await env.TOKENS.put("last_engage", String(nowMs));
  }
  // 6. alerts.step: buffer check
  const q = await sb(env, "/relay_queue?select=scheduled_at,status");
  const rows = q.ok ? await q.json() as any : [];
  const future = rows.filter((r: any) => r.status === "scheduled").map((r: any) => new Date(r.scheduled_at).getTime());
  const bufferDays = future.length ? (Math.max(...future) - Date.now()) / 86400000 : 0;
  await env.TOKENS.put("buffer_days", String(bufferDays));
  if (bufferDays < 3) {
    await dedupeAlert(env, "buffer_low", `Buffer low: ${bufferDays.toFixed(1)} days left. Turn on the laptop and leave it on for about 2 hours.`);
  }
  // daily/weekly handled by separate cron? keep simple
}