import { Env, sb, sbRpc } from "./db";
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
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
}

async function hmacSha256(secret: string, msg: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(msg));
  return Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

export async function handleFactoryApi(env: Env, request: Request, path: string): Promise<Response> {
  const ok = await verify(env, request, path);
  if (!ok) return new Response("not found", { status: 404 });
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
    if (!r.ok) return new Response("storage error", { status: 500 });
    const j: any = await r.json();
    const signed = base + (j.url || "");
    const publicUrl = base + "/storage/v1/object/public/media/" + objectPath;
    return json({ url: signed, public_url: publicUrl, path: objectPath });
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
    // supabase check
    let supabase_ok = false;
    try {
      const r = await sb(env, "/relay_state?limit=1");
      supabase_ok = r.ok;
    } catch (e) { supabase_ok = false; }
    // kv check
    let kv_ok = false;
    try {
      await env.TOKENS.get("ping");
      kv_ok = true;
    } catch (e) { kv_ok = false; }
    // telegram check
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