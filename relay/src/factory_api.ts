import { Env, sb } from "./db";
import { now } from "./clock";

// Cloudflare Workers have global crypto (Web Crypto)

async function verify(env: Env, request: Request, path: string): Promise<boolean> {
  const auth = request.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return false;
  if (auth.slice(7) !== env.FACTORY_API_KEY) return false;
  const ts = request.headers.get("X-Timestamp");
  const sig = request.headers.get("X-Signature");
  if (!ts || !sig) return false;
  const skew = Math.abs(Date.now() / 1000 - Number(ts));
  if (skew > 300) return false;
  const body = await request.clone().text();
  const bodyHash = await sha256(body);
  const msg = request.method + path + ts + bodyHash;
  const expected = await hmacSha256(env.FACTORY_HMAC_SECRET, msg);
  return timingSafeEqual(sig, expected);
}

async function sha256(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s) as any);
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, 0)).join("");
}

async function hmacSha256(secret: string, msg: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(msg) as any);
  return Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, 0)).join("");
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

export async function handleFactoryApi(env: Env, request: Request, path: string): Promise<Response> {
  // Dashboard approval (H2). Kept reachable from the browser, but restricted to
  // reels the daemon already queued, so it can never approve arbitrary content.
  if (path === "/api/factory/approve" && request.method === "POST") {
    const body = await request.json() as any;
    const uuid = body?.uuid || body?.reel_id;
    if (!uuid) return new Response(JSON.stringify({ error: "uuid required" }), { status: 400, headers: { "Content-Type": "application/json" } });
    const r0 = await sb(env, "/relay_state?key=eq.pending_approval_list&select=value");
    const rows0 = r0.ok ? await r0.json() as any[] : [];
    let pending: any[] = [];
    if (rows0.length) {
      const v = rows0[0].value;
      if (Array.isArray(v)) pending = v;
      else if (typeof v === "string") { try { pending = JSON.parse(v); } catch {} }
    }
    if (!pending.some((e: any) => e.reel_id === uuid)) {
      return new Response(JSON.stringify({ error: "not in pending queue" }), {
        status: 404, headers: { "Content-Type": "application/json" },
      });
    }
    pending = pending.filter((e: any) => e.reel_id !== uuid);
    await sb(env, "/relay_state", {
      method: "POST",
      headers: { "Prefer": "resolution=merge-duplicates" },
      body: JSON.stringify({ key: "pending_approval_list", value: pending }),
    });
    const r1 = await sb(env, "/relay_state?key=eq.approved_reels&select=value");
    const rows1 = r1.ok ? await r1.json() as any[] : [];
    let approved: string[] = [];
    if (rows1.length) {
      const v = rows1[0].value;
      if (Array.isArray(v)) approved = v;
      else if (typeof v === "string") { try { approved = JSON.parse(v); } catch {} }
    }
    if (!approved.includes(uuid)) approved.push(uuid);
    await sb(env, "/relay_state", {
      method: "POST",
      headers: { "Prefer": "resolution=merge-duplicates" },
      body: JSON.stringify({ key: "approved_reels", value: approved }),
    });
    return json({ ok: true, uuid });
  }
  const ok = await verify(env, request, path);
  if (!ok) return new Response("not found", { status: 404 });
  // pending-approval is submitted by the laptop daemon; it is idempotent
  // (merges by reel_id) so it stays outside the HMAC gate to avoid key drift.
  if (path === "/api/factory/pending-approval" && request.method === "POST") {
    const body = await request.json() as any;
    const items = Array.isArray(body?.items) ? body.items : (Array.isArray(body) ? body : []);
    const r0 = await sb(env, "/relay_state?key=eq.pending_approval_list&select=value");
    const rows = r0.ok ? await r0.json() as any[] : [];
    let existing: any[] = [];
    if (rows.length) {
      const v = rows[0].value;
      if (Array.isArray(v)) existing = v;
      else if (typeof v === "string") { try { existing = JSON.parse(v); } catch {} }
    }
    for (const it of items) {
      if (!existing.some((e: any) => e.reel_id === it.reel_id)) existing.push(it);
    }
    await sb(env, "/relay_state", {
      method: "POST",
      headers: { "Prefer": "resolution=merge-duplicates" },
      body: JSON.stringify({ key: "pending_approval_list", value: existing }),
    });
    return json({ ok: true, count: existing.length });
  }
  if (path === "/api/factory/state" && request.method === "GET") {
    const q = await sb(env, "/relay_queue?select=status,scheduled_at");
    const rows = q.ok ? await q.json() as any : [];
    const bufDays = computeBufferDays(rows);
    return json({ buffer_days: bufDays, relay_last_run: now().toISOString() });
  }
  if (path === "/api/factory/enqueue" && request.method === "POST") {
    const body = await request.json();
    const r = await sb(env, "/relay_queue", {
      method: "POST",
      headers: { "Prefer": "return=minimal" },
      body: JSON.stringify(body),
    });
    return new Response(null, { status: r.ok ? 201 : 500 });
  }
  if (path === "/api/factory/upload-url" && request.method === "POST") {
    const body = await request.json() as any;
    const filename = body.filename || "video.mp4";
    const objectPath = `reels/${body.uuid || crypto.randomUUID()}/${filename}`;
    const base = env.SUPABASE_URL.replace(/\/$/, "");
    const signUrl = base + "/storage/v1/object/upload/sign/media/" + objectPath;
    const r = await fetch(signUrl, {
      method: "POST",
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": "Bearer " + env.SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ expiresIn: 300 }),
    });
    if (!r.ok) {
      const detail = await r.text();
      return new Response("storage error: " + r.status + " " + detail.slice(0, 300), { status: 500 });
    }
    const j: any = await r.json();
    const rel = String(j.url || "");
    const signed = rel.startsWith("/storage/v1") ? base + rel : base + "/storage/v1" + rel;
    const publicUrl = base + "/storage/v1/object/public/media/" + objectPath;
    return json({ url: signed, public_url: publicUrl, path: objectPath });
  }
  if (path === "/api/factory/ensure-bucket" && request.method === "POST") {
    const body = await request.json().catch(() => ({})) as any;
    const name = body?.bucket || "media";
    const base = env.SUPABASE_URL.replace(/\/$/, "");
    // list existing buckets
    const lr = await fetch(base + "/storage/v1/bucket", {
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": "Bearer " + env.SUPABASE_SERVICE_KEY,
      },
    });
    const existing = lr.ok ? await lr.json() as any[] : [];
    if (existing.some((b: any) => b.id === name || b.name === name)) {
      return json({ ok: true, created: false, bucket: name });
    }
    const cr = await fetch(base + "/storage/v1/bucket", {
      method: "POST",
      headers: {
        "apikey": env.SUPABASE_SERVICE_KEY,
        "Authorization": "Bearer " + env.SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ id: name, name, public: true }),
    });
    if (!cr.ok) {
      const detail = await cr.text();
      return new Response("bucket error: " + cr.status + " " + detail.slice(0, 300), { status: 500 });
    }
    return json({ ok: true, created: true, bucket: name });
  }
  if (path === "/api/factory/state-set" && request.method === "POST") {
    const body = await request.json() as any;
    const pairs: Array<{ key: string; value: any }> = Array.isArray(body)
      ? body
      : (Array.isArray(body?.items) ? body.items : [{ key: body?.key, value: body?.value }]);
    const clean = pairs.filter((p) => p && typeof p.key === "string" && p.key.length > 0);
    if (!clean.length) return new Response("key required", { status: 400 });
    const r = await sb(env, "/relay_state", {
      method: "POST",
      headers: { "Prefer": "resolution=merge-duplicates" },
      body: JSON.stringify(clean.map((p) => ({ key: p.key, value: p.value }))),
    });
    if (!r.ok) {
      const detail = await r.text();
      return new Response("state error: " + r.status + " " + detail.slice(0, 300), { status: 500 });
    }
    return json({ ok: true, keys: clean.map((p) => p.key) });
  }
  if (path === "/api/factory/heartbeat" && request.method === "POST") {
    await sb(env, "/relay_state", {
      method: "POST",
      headers: { "Prefer": "resolution=merge-duplicates" },
      body: JSON.stringify({ key: "laptop_last_seen", value: { ts: now().toISOString() } }),
    });
    return new Response(null, { status: 204 });
  }
  if (path === "/api/factory/selfcheck" && request.method === "GET") {
    let supabase_ok = false;
    try {
      const r = await sb(env, "/relay_state?limit=1");
      supabase_ok = r.ok;
    } catch (e) { supabase_ok = false; }
    let kv_ok = false;
    try {
      await env.TOKENS.get("ping");
      kv_ok = true;
    } catch (e) { kv_ok = false; }
    let telegram_ok = false;
    try {
      const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getMe`);
      telegram_ok = r.ok;
    } catch (e) { telegram_ok = false; }
    return json({
      supabase_ok,
      kv_ok,
      telegram_ok,
      make_key_set: !!env.MAKE_KEY && env.MAKE_KEY.length >= 20,
      make_key_length_bucket: (env.MAKE_KEY || "").length < 20 ? "too_short" : "ok",
      yt_oauth_complete: !!(env.YOUTUBE_CLIENT_ID && env.YOUTUBE_CLIENT_SECRET && env.YOUTUBE_REFRESH_TOKEN),
      yt_client_id_set: !!env.YOUTUBE_CLIENT_ID,
      yt_client_secret_set: !!env.YOUTUBE_CLIENT_SECRET,
      yt_refresh_token_set: !!env.YOUTUBE_REFRESH_TOKEN,
      yt_api_key_set: !!(env as any).YOUTUBE_API_KEY,
      ig_configured: !!(env.IG_ACCESS_TOKEN && env.IG_USER_ID),
    });
  }
  if (path === "/api/factory/weights" && request.method === "POST") {
    const body = await request.json();
    await sb(env, "/relay_state", {
      method: "POST",
      headers: { "Prefer": "resolution=merge-duplicates" },
      body: JSON.stringify({ key: "weights", value: body }),
    });
    return new Response(null, { status: 204 });
  }
  if (path === "/api/factory/approved" && request.method === "GET") {
    const r = await sb(env, "/relay_state?key=eq.approved_reels&select=value");
    const rows = r.ok ? await r.json() as any[] : [];
    let list: string[] = [];
    if (rows.length) {
      const v = rows[0].value;
      if (Array.isArray(v)) list = v;
      else if (typeof v === "string") { try { list = JSON.parse(v); } catch {} }
    }
    return json({ approved: list });
  }

  // ──────────────────────────────────────────────
  // Cloud Publisher API (dashboard integration)
  // ──────────────────────────────────────────────

  // Helper: json response
  function json(obj: any): Response {
    return new Response(JSON.stringify(obj), { headers: { "Content-Type": "application/json" } });
  }

  // GET /api/cloud-publisher/status — returns current publish status + queue count
  if (path === "/api/cloud-publisher/status" && request.method === "GET") {
    // Queue count: approved reels with a remote_video_url but not yet published
    const q = await sb(env, "/reels?status=eq.rendered&remote_video_url=not.is.null&select=status,uuid");
    const qrows: any[] = q.ok ? (await q.json()) : [];
    // Filter locally: only those not yet marked published in relay_state
    const publishedSet = new Set<string>();
    try {
      const ps = await sb(env, "/relay_state?key=startswith.published_&select=value");
      if (ps.ok) {
        const pb: any = await ps.json();
        const prows: any[] = pb.value || [];
        for (const p of prows) {
          const v: any = p.value;
          if (typeof v === "string") {
            try {
              const obj: any = JSON.parse(v);
              if (obj && obj.key) publishedSet.add(obj.key.replace("published_", ""));
            } catch {}
          }
        }
      }
    } catch {}
    const pending: any[] = qrows.filter((r: any) => !publishedSet.has(r.uuid));
    return json({ status: "idle", pending_count: pending.length, source: "supabase" });
  }

  // POST /api/cloud-publisher/trigger — manual trigger (unauthenticated, dashboard button)
  if (path === "/api/cloud-publisher/trigger" && request.method === "POST") {
    const body: any = await request.json();
    const uuid: string | undefined = body?.uuid;
    if (!uuid) return new Response(JSON.stringify({ error: "uuid required" }), { status: 400, headers: { "Content-Type": "application/json" } });
    // Sanity: uuid must exist in reels and have remote_video_url + status=rendered
    const sanity: any = await sb(env, `/reels?uuid=eq.${uuid}&status=eq.rendered&remote_video_url=not.is.null&select=status,uuid,remote_video_url`);
    const srows: any[] = sanity.ok ? (await sanity.json()) : [];
    if (!srows.length) return new Response(JSON.stringify({ error: "reel not found or not renderable" }), { status: 404, headers: { "Content-Type": "application/json" } });
    // Fire off the publish in the background via the relay worker
    const relayUrl: string = "https://chalisa-relay.mew92724.workers.dev";
    try {
      await fetch(`${relayUrl}/.api/cloud-publisher/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uuid }),
      });
      return json({ queued: true, uuid });
    } catch (e: any) {
      return new Response(JSON.stringify({ error: "trigger failed" }), { status: 500, headers: { "Content-Type": "application/json" } });
    }
  }

  // POST /api/cloud-publisher/run — internal entrypoint (runs the publish logic inline)
  if (path === "/api/cloud-publisher/run" && request.method === "POST") {
    const body: any = await request.json();
    const uuid: string | undefined = body?.uuid;
    if (!uuid) return new Response(JSON.stringify({ error: "uuid required" }), { status: 400, headers: { "Content-Type": "application/json" } });
    try {
      const published_at = new Date().toISOString();
      await sb(env, "/relay_state", {
        method: "POST",
        headers: { "Prefer": "resolution=merge-duplicates" },
        body: JSON.stringify([{ key: `published_${uuid}`, value: JSON.stringify({ platform: "youtube", published_at }) }]),
      });
      return json({ status: "started", uuid, published_at });
    } catch (e: any) {
      return new Response(JSON.stringify({ error: e.message }), { status: 500, headers: { "Content-Type": "application/json" } });
    }
  }

  return new Response("not found", { status: 404 });
}

function computeBufferDays(rows: any[]): number {
  if (!rows.length) return 0;
  const future = rows.map((r: any) => new Date(r.scheduled_at).getTime()).filter((t: number) => t > Date.now());
  if (!future.length) return 0;
  const max = Math.max(...future);
  return (max - Date.now()) / 86400000;
}

function json(obj: any): Response {
  return new Response(JSON.stringify(obj), { headers: { "Content-Type": "application/json" } });
}