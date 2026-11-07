import { Env, sb, sbRpc } from "./db";
import { now } from "./clock";
import { getToken, refreshIfNeeded } from "./tokens";
import { telegram } from "./alerts";

export async function stepPublisher(env: Env): Promise<void> {
  // token refresh monthly
  await refreshIfNeeded(env);
  // advance in-flight
  const inflight = await sb(env, "/relay_queue?status=in.(container_created,publishing)&limit=1");
  const rows = inflight.ok ? await inflight.json() as any : [];
  if (rows.length) {
    const r = rows[0];
    if (r.status === "container_created" && r.ig_container_id) {
      // poll container status
      const token = await getToken(env);
      const st = await fetch(`https://graph.instagram.com/v21.0/${r.ig_container_id}?fields=status_code&access_token=${token}`);
      const j: any = await st.json();
      if (j.status_code === "FINISHED") {
        // media_publish
        const pub = await fetch(`https://graph.instagram.com/v21.0/${env.IG_USER_ID}/media_publish`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ creation_id: r.ig_container_id, access_token: token! }),
        });
        const pj: any = await pub.json();
        if (pj.id) {
          await sb(env, `/relay_queue?id=eq.${r.id}`, {
            method: "PATCH",
            body: JSON.stringify({ status: "published", ig_media_id: pj.id, published_at: now().toISOString() }),
          });
        }
      } else if (j.status_code === "ERROR") {
        await sb(env, `/relay_queue?id=eq.${r.id}`, {
          method: "PATCH",
          body: JSON.stringify({ status: "failed", last_error: "container error" }),
        });
      }
    }
    return;
  }
  // claim due
  const claim = await sbRpc(env, "claim_due_reel", { worker: "relay" });
  const claimed = claim.ok ? await claim.json() as any : [];
  const row = Array.isArray(claimed) ? claimed[0] : claimed;
  if (!row || !row.id) return;
  // max late hours
  const scheduled = new Date(row.scheduled_at).getTime();
  const lateH = (Date.now() - scheduled) / 3600000;
  if (lateH > 4) {
    // reschedule to next free slot (simplified: +1 day)
    await sb(env, `/relay_queue?id=eq.${row.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "scheduled", scheduled_at: new Date(Date.now() + 86400000).toISOString(), claimed_by: null, claimed_at: null }),
    });
    return;
  }
  // preflight HEAD video_url
  try {
    const head = await fetch(row.video_url, { method: "HEAD" });
    if (!head.ok) throw new Error("preflight fail");
  } catch (e) {
    await sb(env, `/relay_queue?id=eq.${row.id}`, { method: "PATCH", body: JSON.stringify({ status: "scheduled", claimed_by: null, claimed_at: null, last_error: String(e) }) });
    return;
  }
  // create container
  const token = await getToken(env);
  const params = new URLSearchParams({
    media_type: "REELS",
    video_url: row.video_url,
    caption: row.caption || "",
    access_token: token!,
  });
  const cr = await fetch(`https://graph.instagram.com/v21.0/${env.IG_USER_ID}/media`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: params,
  });
  const cj: any = await cr.json();
  if (cj.id) {
    await sb(env, `/relay_queue?id=eq.${row.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "container_created", ig_container_id: cj.id }),
    });
  } else {
    await sb(env, `/relay_queue?id=eq.${row.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "scheduled", claimed_by: null, claimed_at: null, last_error: JSON.stringify(cj), attempts: (row.attempts || 0) + 1 }),
    });
  }
}