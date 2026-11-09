import { Env, sb } from "./db";
import { now } from "./clock";

// Free YouTube Data API quota is 10,000 units/day and a video upload costs ~1600
// units, so five uploads/day is the safe ceiling for this project.
export const YOUTUBE_DAILY_LIMIT = 5;

export function youtubeEnabled(env: Env): boolean {
  // Uploads need both an explicit switch and a refresh token; neither is set by default.
  return env.YOUTUBE_ENABLED === "true" && !!env.YOUTUBE_REFRESH_TOKEN;
}

/** Delegations already recorded for the current UTC day (0 when the meter is stale). */
async function delegatedToday(env: Env, day: string): Promise<number> {
  const r = await sb(env, "/relay_state?key=eq.yt_steps_day&select=value");
  const rows = r.ok ? (await r.json()) as any[] : [];
  const v = rows.length ? rows[0].value : null;
  if (!v || v.day !== day) return 0;
  return typeof v.count === "number" ? v.count : 0;
}

async function recordDelegation(env: Env, day: string, count: number): Promise<void> {
  await sb(env, "/relay_state", {
    method: "POST",
    headers: { Prefer: "resolution=merge-duplicates" },
    body: JSON.stringify({ key: "yt_steps_day", value: { day, count } }),
  });
}

/**
 * Hand published reels to the factory-side uploader.
 *
 * This Worker cannot stream a video body to YouTube within its limits, so it
 * only *delegates*: it marks a row once with yt_status=delegated_to_factory and
 * leaves yt_video_id NULL until the factory uploads and reports back. The query
 * excludes rows that already have a yt_status, otherwise it would re-mark the
 * same reel on every cron tick.
 */
export async function stepYoutube(env: Env): Promise<void> {
  if (!youtubeEnabled(env)) return;

  const day = now().toISOString().slice(0, 10);
  const used = await delegatedToday(env, day);
  if (used >= YOUTUBE_DAILY_LIMIT) return;

  const r = await sb(
    env,
    "/relay_queue?status=eq.published&yt_video_id=is.null&yt_status=is.null&order=published_at.asc&limit=1",
  );
  const rows = r.ok ? ((await r.json()) as any[]) : [];
  if (!rows.length) return;

  const row = rows[0];
  const res = await sb(env, `/relay_queue?id=eq.${row.id}&yt_status=is.null`, {
    method: "PATCH",
    body: JSON.stringify({ yt_status: "delegated_to_factory" }),
  });
  // Only count the delegation if the conditional PATCH actually claimed the row.
  if (res.ok) await recordDelegation(env, day, used + 1);
}
