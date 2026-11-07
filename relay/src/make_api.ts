import { Env, sb } from "./db";
import { now } from "./clock";

async function verifyMake(env: Env, request: Request): Promise<boolean> {
  const auth = request.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return false;
  const token = auth.slice(7);
  if (token.length !== env.MAKE_KEY.length) return false;
  let r = 0;
  for (let i = 0; i < token.length; i++) r |= token.charCodeAt(i) ^ env.MAKE_KEY.charCodeAt(i);
  return r === 0;
}

export async function handleMakeApi(env: Env, request: Request, path: string): Promise<Response> {
  const ok = await verifyMake(env, request);
  if (!ok) return new Response("not found", { status: 404 });

  if (path === "/api/make/ping" && request.method === "GET") {
    await sb(env, "/relay_state", {
      method: "POST",
      headers: { "Prefer": "resolution=merge-duplicates" },
      body: JSON.stringify({ key: "make_last_call", value: { ts: now().toISOString(), test: request.url.includes("test=1") } }),
    });
    return new Response(JSON.stringify({ ok: true, sample: { reel_id: "sample", video_url: "https://example.com/v.mp4", caption: "sample", first_comment: "hi", insight_media_id: null } }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  if (path === "/api/make/next" && request.method === "GET") {
    const url = new URL(request.url);
    const slot = url.searchParams.get("slot") || "A";
    // check posting_enabled
    const st = await sb(env, "/relay_state?key=eq.posting_enabled&select=value");
    const stRows = st.ok ? await st.json() as any : [];
    if (stRows.length && stRows[0].value === false) {
      return json({ empty: true });
    }
    const windowMs = 10 * 60 * 1000;
    const cutoff = new Date(Date.now() + windowMs).toISOString();
    const q = await sb(env, `/relay_queue?status=eq.scheduled&scheduled_at=lte.${cutoff}&order=scheduled_at.asc&limit=1`);
    const rows = q.ok ? await q.json() as any : [];
    if (!rows.length) {
      // reserve reel
      const rq = await sb(env, "/relay_queue?status=eq.scheduled&is_reserve=eq.true&limit=1");
      const rrows = rq.ok ? await rq.json() as any : [];
      if (!rrows.length) {
        await recordMakeCall(env);
        return json({ empty: true });
      }
      const rr = rrows[0];
      await claimReel(env, rr.id);
      await recordMakeCall(env);
      return json({ empty: false, reel_id: rr.id, video_url: rr.video_url, caption: rr.caption, first_comment: rr.first_comment, insight_media_id: null });
    }
    const row = rows[0];
    await claimReel(env, row.id);
    // insight piggyback
    const insightMedia = await pickInsightMedia(env);
    await recordMakeCall(env);
    return json({ empty: false, reel_id: row.id, video_url: row.video_url, caption: row.caption, first_comment: row.first_comment, insight_media_id: insightMedia });
  }

  if (path === "/api/make/ack" && request.method === "POST") {
    const body = await request.json() as any;
    const { reel_id, status, ig_media_id, permalink, message } = body;
    if (status === "ok") {
      await sb(env, `/relay_queue?id=eq.${reel_id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "published", ig_media_id, permalink, acked_at: now().toISOString(), ack_status: "ok" }),
      });
      // trigger youtube step is handled by cron
    } else {
      await sb(env, `/relay_queue?id=eq.${reel_id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "failed_in_make", ack_status: "error", make_run_note: message, last_error: message }),
      });
      await (await import("./alerts")).telegram(env, `Make failed: reel ${reel_id}: ${message}`);
    }
    return new Response(null, { status: 204 });
  }

  if (path === "/api/make/insights" && request.method === "POST") {
    const body = await request.json() as any;
    const { media_id, metrics } = body;
    await sb(env, "/relay_insights", {
      method: "POST",
      body: JSON.stringify({ media_id, fetched_at: now().toISOString(), ...metrics }),
    });
    return new Response(null, { status: 204 });
  }

  return new Response("not found", { status: 404 });
}

async function claimReel(env: Env, id: string) {
  await sb(env, `/relay_queue?id=eq.${id}&status=eq.scheduled`, {
    method: "PATCH",
    body: JSON.stringify({ status: "handed_off", handed_off_at: now().toISOString() }),
  });
}

async function recordMakeCall(env: Env) {
  await sb(env, "/relay_state", {
    method: "POST",
    headers: { "Prefer": "resolution=merge-duplicates" },
    body: JSON.stringify({ key: "make_last_call", value: { ts: now().toISOString() } }),
  });
  // credit meter
  const r = await sb(env, "/relay_state?key=eq.make_calls_month&select=value");
  const rows = r.ok ? await r.json() as any : [];
  const prev = rows.length ? rows[0].value?.count || 0 : 0;
  await sb(env, "/relay_state", {
    method: "POST",
    headers: { "Prefer": "resolution=merge-duplicates" },
    body: JSON.stringify({ key: "make_calls_month", value: { count: prev + 1 } }),
  });
}

async function pickInsightMedia(env: Env): Promise<string | null> {
  const r = await sb(env, "/relay_queue?status=eq.published&yt_video_id=is.null&order=published_at.asc&limit=1&select=ig_media_id");
  // simplified: return oldest published media_id
  const rows = r.ok ? await r.json() as any : [];
  return rows.length ? rows[0].ig_media_id : null;
}

function json(obj: any): Response {
  return new Response(JSON.stringify(obj), { headers: { "Content-Type": "application/json" } });
}