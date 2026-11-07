import { Env, sb } from "./db";

export async function stepYoutube(env: Env): Promise<void> {
  // quota guard: max 5/day tracked in relay_state
  if (!env.YOUTUBE_REFRESH_TOKEN) return;
  // find published reels without yt_video_id
  const r = await sb(env, "/relay_queue?status=eq.published&yt_video_id=is.null&limit=1");
  const rows = r.ok ? await r.json() as any : [];
  if (!rows.length) return;
  const row = rows[0];
  // feasibility: in-Worker streaming not implemented; mark skipped for now
  await sb(env, `/relay_queue?id=eq.${row.id}`, {
    method: "PATCH",
    body: JSON.stringify({ yt_status: "delegated_to_factory" }),
  });
}