import { Env, sb, sbRpc } from "./db";
import { now } from "./clock";
import { dedupeAlert, telegram } from "./alerts";

// Make.com polling contract. The relay owns the state machine:
//   scheduled --claim_due_reel--> claimed --next--> handed_off --ack--> published | failed_in_make
// A handed_off row with no ack ages into `unknown` (make_health.ts), and a
// repeated /next within MAKE_CLAIM_WINDOW_MINUTES returns the same row instead
// of handing out a second one.

function intEnv(value: string | undefined, def: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : def;
}

function claimWindowMinutes(env: Env): number {
  return intEnv(env.MAKE_CLAIM_WINDOW_MINUTES, 10);
}

function monthKey(): string {
  return now().toISOString().slice(0, 7);
}

function minuteKey(): string {
  return now().toISOString().slice(0, 16);
}

async function readState(env: Env, key: string): Promise<any> {
  const r = await sb(env, `/relay_state?key=eq.${encodeURIComponent(key)}&select=value`);
  const rows = r.ok ? ((await r.json()) as any[]) : [];
  return rows.length ? rows[0].value : null;
}

async function writeState(env: Env, key: string, value: any): Promise<void> {
  await sb(env, "/relay_state", {
    method: "POST",
    headers: { Prefer: "resolution=merge-duplicates" },
    body: JSON.stringify({ key, value }),
  });
}

async function verifyMake(env: Env, request: Request): Promise<boolean> {
  const auth = request.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return false;
  const token = auth.slice(7);
  if (token.length !== env.MAKE_KEY.length) return false;
  let r = 0;
  for (let i = 0; i < token.length; i++) r |= token.charCodeAt(i) ^ env.MAKE_KEY.charCodeAt(i);
  return r === 0;
}

/** Missing row keeps the legacy "enabled" behaviour; an explicit false disables. */
async function postingEnabled(env: Env): Promise<boolean> {
  const v = await readState(env, "posting_enabled");
  if (v === undefined || v === null) return true;
  if (typeof v === "boolean") return v;
  if (typeof v === "string") return v.toLowerCase() === "true";
  if (typeof v === "object" && "enabled" in v) return !!v.enabled;
  return true;
}

async function rateLimited(env: Env): Promise<boolean> {
  const limit = intEnv(env.MAKE_MAX_CALLS_PER_MINUTE, 60);
  const bucket = minuteKey();
  const cur = await readState(env, "make_rate");
  const count = cur && cur.minute === bucket && typeof cur.count === "number" ? cur.count : 0;
  if (count >= limit) return true;
  await writeState(env, "make_rate", { minute: bucket, count: count + 1 });
  return false;
}

async function touch(env: Env, test: boolean): Promise<void> {
  await writeState(env, "make_last_call", { ts: now().toISOString(), test });
}

async function recentHandoff(env: Env): Promise<any | null> {
  const r = await sb(
    env,
    "/relay_queue?status=eq.handed_off&ack_status=is.null&order=handed_off_at.desc&limit=1",
  );
  const rows = r.ok ? ((await r.json()) as any[]) : [];
  if (!rows.length || !rows[0].handed_off_at) return null;
  const ageMin = (Date.now() - new Date(rows[0].handed_off_at).getTime()) / 60000;
  return ageMin <= claimWindowMinutes(env) ? rows[0] : null;
}

async function claimDue(env: Env): Promise<any | null> {
  const claim = await sbRpc(env, "claim_due_reel", { worker: "make" });
  if (!claim.ok) throw new Error(`claim_due_reel failed: ${claim.status}`);
  const body = await claim.json();
  const row = Array.isArray(body) ? body[0] : body;
  return row && row.id ? row : null;
}

/** Atomically move claimed -> handed_off, so two Make runs cannot both take it. */
async function handoff(env: Env, id: string): Promise<boolean> {
  const r = await sb(env, `/relay_queue?id=eq.${id}&status=eq.claimed`, {
    method: "PATCH",
    headers: { Prefer: "return=representation" },
    body: JSON.stringify({ status: "handed_off", handed_off_at: now().toISOString() }),
  });
  if (!r.ok) return false;
  if (r.status === 204) return true;
  const rows = await r.json() as any[];
  return Array.isArray(rows) ? rows.length > 0 : true;
}

async function credits(env: Env): Promise<{ used: number; max: number }> {
  const budget = intEnv(env.MAKE_CREDITS_BUDGET_MONTHLY, 800);
  const perRun = intEnv(env.MAKE_CREDITS_PER_RUN, 6);
  const max = Math.floor(budget / perRun);
  const cur = await readState(env, "make_handoffs_month");
  const used = cur && cur.month === monthKey() && typeof cur.count === "number" ? cur.count : 0;
  return { used, max };
}

async function bumpHandoffs(env: Env, used: number): Promise<void> {
  await writeState(env, "make_handoffs_month", { month: monthKey(), count: used + 1 });
}

/** Budget alerts: warn at 80%, stop handing off at 100%. */
async function creditGate(env: Env): Promise<boolean> {
  const { used, max } = await credits(env);
  if (used >= max) {
    await dedupeAlert(env, `make_credits:${monthKey()}`,
      `Make credits exhausted: ${used}/${max} runs used this month. Posting from Make is paused.`);
    return false;
  }
  if (max > 0 && used >= max * 0.8) {
    await dedupeAlert(env, `make_credits_80:${monthKey()}`,
      `Make credits at ${used}/${max} runs this month.`);
  }
  return true;
}

export async function recoverStuck(env: Env): Promise<void> {
  const cutoff = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  const r = await sb(env, `/relay_queue?status=in.(handed_off,unknown)&retry_count=lt.3&handed_off_at=lt.${encodeURIComponent(cutoff)}&select=id,retry_count`);
  const rows = r.ok ? ((await r.json()) as any[]) : [];
  for (const row of rows) {
    await sb(env, `/relay_queue?id=eq.${encodeURIComponent(row.id)}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "planned", claimed: false, retry_count: (row.retry_count || 0) + 1, last_error: "make timeout recovery" }),
    });
    await sb(env, "/relay_errors", {
      method: "POST",
      body: JSON.stringify({ component: "make_api", reel_id: row.id, message: "handoff timeout recovery", payload: { retry: (row.retry_count || 0) + 1 } }),
    });
  }
}
async function pickInsightMedia(env: Env): Promise<string | null> {
  const r = await sb(env, "/relay_queue?status=eq.published&ig_media_id=not.is.null&order=published_at.asc&limit=1&select=ig_media_id");
  const rows = r.ok ? ((await r.json()) as any[]) : [];
  return rows.length ? rows[0].ig_media_id : null;
}

function reelPayload(row: any, insight: string | null) {
  return {
    empty: false,
    reel_id: row.id,
    video_url: row.video_url,
    caption: row.caption,
    first_comment: row.first_comment,
    insight_media_id: insight,
  };
}

async function getRow(env: Env, id: string): Promise<any | null> {
  const r = await sb(env, `/relay_queue?id=eq.${encodeURIComponent(id)}&select=*`);
  const rows = r.ok ? ((await r.json()) as any[]) : [];
  return rows.length ? rows[0] : null;
}

export async function handleMakeApi(env: Env, request: Request, path: string): Promise<Response> {
  const ok = await verifyMake(env, request);
  if (!ok) return new Response("not found", { status: 404 });

  if (path === "/api/make/ping" && request.method === "GET") {
    await touch(env, request.url.includes("test=1"));
    return json({
      ok: true,
      sample: {
        reel_id: "sample",
        video_url: "https://example.com/v.mp4",
        caption: "sample",
        first_comment: "hi",
        insight_media_id: null,
      },
    });
  }

  if (path !== "/api/make/next" && path !== "/api/make/ack") {
    return handleRemaining(env, request, path);
  }

  if (await rateLimited(env)) {
    return new Response(JSON.stringify({ ok: false, error: "rate_limited" }), {
      status: 429,
      headers: { "Content-Type": "application/json", "Retry-After": "60" },
    });
  }

  if (path === "/api/make/next" && request.method === "GET") {
    await touch(env, request.url.includes("test=1"));
    if (!(await postingEnabled(env))) return json({ empty: true, reason: "posting_disabled" });
    if (!(await creditGate(env))) return json({ empty: true, reason: "credit_budget" });

    // Idempotency: Make may retry the same poll; do not hand out a second reel.
    const recent = await recentHandoff(env);
    if (recent) return json(reelPayload(recent, null));

    // Recovery: re-queue reels stuck in handed_off/unknown for > 60 min.
    try { await recoverStuck(env); } catch (e) { /* best effort */ }

    const row = await claimDue(env);
    if (!row) return json({ empty: true, reason: "none_due" });
    if (!(await handoff(env, row.id))) return json({ empty: true, reason: "claim_lost" });

    const { used } = await credits(env);
    await bumpHandoffs(env, used);
    const insight = await pickInsightMedia(env);
    return json(reelPayload({ ...row, status: "handed_off" }, insight));
  }

  if (path === "/api/make/ack" && request.method === "POST") {
    return handleAck(env, request);
  }

  return new Response("not found", { status: 404 });
}

async function handleAck(env: Env, request: Request): Promise<Response> {
  const body = (await request.json()) as any;
  const { reel_id, status, ig_media_id, permalink, message } = body;
  if (!reel_id) return json({ ok: false, error: "missing reel_id" }, 400);

  const cur = await getRow(env, reel_id);
  // Ack is idempotent: a terminal result is recorded once, retries get 204.
  if (cur && (cur.ack_status === "ok" || cur.status === "published" || cur.status === "failed_in_make")) {
    return new Response(null, { status: 204 });
  }

  if (status === "ok") {
    await sb(env, `/relay_queue?id=eq.${encodeURIComponent(reel_id)}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: "published",
        ig_media_id,
        permalink,
        acked_at: now().toISOString(),
        ack_status: "ok",
        last_error: null,
      }),
    });
  } else {
    await sb(env, `/relay_queue?id=eq.${encodeURIComponent(reel_id)}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: "failed_in_make",
        ack_status: "error",
        acked_at: now().toISOString(),
        make_run_note: message,
        last_error: message,
      }),
    });
    await sb(env, "/relay_errors", {
      method: "POST",
      body: JSON.stringify({ component: "make_api", reel_id: reel_id, message: String(message || "make failed"), payload: { status } }),
    });
    await telegram(env, `Make failed: reel ${reel_id}: ${message}`);
  }
  return new Response(null, { status: 204 });
}

async function handleRemaining(env: Env, request: Request, path: string): Promise<Response> {
  if (path === "/api/make/insights" && request.method === "POST") {
    const body = (await request.json()) as any;
    const { media_id, metrics } = body;
    await sb(env, "/relay_insights", {
      method: "POST",
      body: JSON.stringify({ media_id, fetched_at: now().toISOString(), ...metrics }),
    });
    return new Response(null, { status: 204 });
  }
  return new Response("not found", { status: 404 });
}

function json(obj: any, status = 200): Response {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
