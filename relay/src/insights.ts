import { Env, sb } from "./db";
import { getToken } from "./tokens";

const METRICS = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions"];

export async function snapshotInsights(env: Env, mediaId: string, hoursSince: number) {
  const token = await getToken(env);
  const m = METRICS.join(",");
  const r = await fetch(`https://graph.instagram.com/v21.0/${mediaId}/insights?metric=${m}&access_token=${token}`);
  const j: any = await r.json();
  const data = j.data || [];
  const get = (name: string) => {
    const item = data.find((d: any) => d.name === name);
    return item ? item.values?.[0]?.value ?? null : null;
  };
  const views = get("views");
  const reach = get("reach");
  const avgWatch = null;
  const dur = 40;
  const completion = avgWatch ? avgWatch / (dur * 1000) : null;
  await sb(env, "/relay_insights", {
    method: "POST",
    body: JSON.stringify({
      media_id: mediaId,
      hours_since_post: hoursSince,
      views, reach,
      likes: get("likes"),
      comments: get("comments"),
      shares: get("shares"),
      saves: get("saved"),
      avg_watch_ms: avgWatch,
      total_watch_ms: null,
      completion_ratio: completion,
      raw: j,
    }),
  });
}

export async function dailyAccountSnapshot(env: Env) {
  // placeholder: store followers
  await sb(env, "/relay_account", {
    method: "POST",
    headers: { "Prefer": "resolution=merge-duplicates" },
    body: JSON.stringify({ day: new Date().toISOString().slice(0, 10), followers: 0 }),
  });
}