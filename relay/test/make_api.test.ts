import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { handleMakeApi } from "../src/make_api";

const KEY = "mk_test123456789012345678901234567890";

type Row = {
  id: string;
  status: string;
  ack_status?: string | null;
  handed_off_at?: string | null;
  scheduled_at?: string;
  video_url?: string;
  caption?: string;
  first_comment?: string;
  ig_media_id?: string | null;
  permalink?: string | null;
  make_run_note?: string | null;
  last_error?: string | null;
};

let rows: Row[];
let state: Record<string, any>;
let patches: { query: string; body: any }[];
let rpcCalls: number;
let kv: Map<string, string>;

const month = () => new Date().toISOString().slice(0, 7);

function makeEnv(over: Record<string, any> = {}) {
  return {
    SUPABASE_URL: "https://sb.test",
    SUPABASE_SERVICE_KEY: "k",
    MAKE_KEY: KEY,
    TELEGRAM_BOT_TOKEN: "",
    TELEGRAM_CHAT_ID: "",
    MAKE_MAX_CALLS_PER_MINUTE: "1000",
    TOKENS: {
      get: async (k: string) => kv.get(k) ?? null,
      put: async (k: string, v: string) => { kv.set(k, v); },
    },
    ...over,
  } as any;
}

function req(path: string, init: { method?: string; body?: any } = {}) {
  return new Request(`https://x${path}`, {
    method: init.method ?? "GET",
    headers: { Authorization: `Bearer ${KEY}`, "Content-Type": "application/json" },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
}

const next = (env: any) => handleMakeApi(env, req("/api/make/next"), "/api/make/next");
const ack = (env: any, body: any) =>
  handleMakeApi(env, req("/api/make/ack", { method: "POST", body }), "/api/make/ack");

beforeEach(() => {
  rows = [];
  state = {};
  patches = [];
  rpcCalls = 0;
  kv = new Map();

  vi.stubGlobal("fetch", vi.fn(async (input: any, init?: any) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const sp = url.searchParams;

    if (url.pathname === "/rest/v1/relay_state") {
      if (method === "POST") {
        const body = JSON.parse(init.body);
        state[body.key] = body.value;
        return new Response(null, { status: 201 });
      }
      const key = (sp.get("key") ?? "").replace(/^eq\./, "");
      const value = state[key];
      return new Response(JSON.stringify(value === undefined ? [] : [{ key, value }]), { status: 200 });
    }

    if (url.pathname === "/rest/v1/rpc/claim_due_reel") {
      rpcCalls += 1;
      const row = rows.find(r => r.status === "scheduled");
      if (!row) return new Response("[]", { status: 200 });
      row.status = "claimed";
      return new Response(JSON.stringify([row]), { status: 200 });
    }

    if (url.pathname === "/rest/v1/relay_queue") {
      const idEq = (sp.get("id") ?? "").replace(/^eq\./, "");
      const statusEq = (sp.get("status") ?? "").replace(/^eq\./, "");
      const ackNull = sp.get("ack_status") === "is.null";
      const matched = rows.filter(r =>
        (!idEq || r.id === idEq) &&
        (!statusEq || r.status === statusEq) &&
        (!ackNull || r.ack_status === null || r.ack_status === undefined),
      );
      if (method === "PATCH") {
        const body = JSON.parse(init.body);
        const headers = new Headers(init?.headers ?? {});
        patches.push({ query: url.search, body });
        for (const r of matched) Object.assign(r, body);
        if (headers.get("Prefer") === "return=representation") {
          return new Response(JSON.stringify(matched), { status: 200 });
        }
        return new Response(null, { status: 204 });
      }
      const limit = Number(sp.get("limit") ?? matched.length);
      return new Response(JSON.stringify(matched.slice(0, limit)), { status: 200 });
    }

    return new Response("{}", { status: 201 });
  }));
});

afterEach(() => { vi.unstubAllGlobals(); });

describe("make_api auth", () => {
  it("returns 404 for bad bearer", async () => {
    const env = makeEnv();
    const request = new Request("https://x/api/make/ping?test=1", { headers: { Authorization: "Bearer wrong" } });
    const res = await handleMakeApi(env, request, "/api/make/ping");
    expect(res.status).toBe(404);
  });
});

describe("make_api next state machine", () => {
  it("returns empty when posting_enabled is false", async () => {
    state.posting_enabled = false;
    rows.push({ id: "r1", status: "scheduled" });
    const res = await next(makeEnv());
    expect(await res.json()).toEqual({ empty: true, reason: "posting_disabled" });
    expect(rpcCalls).toBe(0);
  });

  it("claims a due reel through claim_due_reel and marks it handed_off", async () => {
    rows.push({ id: "r1", status: "scheduled", video_url: "https://cdn/v.mp4", caption: "c", first_comment: "f" });
    const res = await next(makeEnv());
    const body = await res.json();

    expect(body.reel_id).toBe("r1");
    expect(body.empty).toBe(false);
    expect(rpcCalls).toBe(1);
    expect(rows[0].status).toBe("handed_off");
    expect(rows[0].handed_off_at).toBeTruthy();
    expect(state.make_handoffs_month).toEqual({ month: month(), count: 1 });
  });

  it("is idempotent within the claim window", async () => {
    rows.push({ id: "r1", status: "scheduled" });
    const env = makeEnv();
    const first = await (await next(env)).json();
    const second = await (await next(env)).json();

    expect(second.reel_id).toBe(first.reel_id);
    expect(rpcCalls).toBe(1);
    expect(state.make_handoffs_month.count).toBe(1);
  });

  it("ignores a stale handoff and claims the next reel", async () => {
    rows.push({
      id: "old",
      status: "handed_off",
      ack_status: null,
      handed_off_at: new Date(Date.now() - 3600_000).toISOString(),
    });
    rows.push({ id: "new", status: "scheduled" });
    const body = await (await next(makeEnv())).json();

    expect(body.reel_id).toBe("new");
    expect(rows.find(r => r.id === "old")!.status).toBe("handed_off");
  });

  it("stops handing off when the monthly credit budget is used up", async () => {
    state.make_handoffs_month = { month: month(), count: 133 };
    rows.push({ id: "r1", status: "scheduled" });
    const body = await (await next(makeEnv())).json();

    expect(body).toEqual({ empty: true, reason: "credit_budget" });
    expect(rpcCalls).toBe(0);
  });

  it("rate limits repeated calls", async () => {
    const env = makeEnv({ MAKE_MAX_CALLS_PER_MINUTE: "1" });
    expect((await next(env)).status).toBe(200);
    expect((await next(env)).status).toBe(429);
  });
});

describe("make_api ack", () => {
  it("publishes on a successful ack", async () => {
    rows.push({ id: "r1", status: "handed_off", ack_status: null });
    const res = await ack(makeEnv(), { reel_id: "r1", status: "ok", ig_media_id: "ig1", permalink: "p" });

    expect(res.status).toBe(204);
    expect(rows[0].status).toBe("published");
    expect(rows[0].ack_status).toBe("ok");
    expect(rows[0].ig_media_id).toBe("ig1");
  });

  it("records an ack failure once", async () => {
    rows.push({ id: "r1", status: "handed_off", ack_status: null });
    await ack(makeEnv(), { reel_id: "r1", status: "error", message: "boom" });

    expect(rows[0].status).toBe("failed_in_make");
    expect(rows[0].ack_status).toBe("error");
    expect(rows[0].make_run_note).toBe("boom");
  });

  it("is idempotent for retried acks", async () => {
    rows.push({ id: "r1", status: "handed_off", ack_status: null });
    const env = makeEnv();
    await ack(env, { reel_id: "r1", status: "ok", ig_media_id: "ig1" });
    const before = patches.length;
    const res = await ack(env, { reel_id: "r1", status: "ok", ig_media_id: "ig1" });

    expect(res.status).toBe(204);
    expect(patches.length).toBe(before);
  });

  it("accepts a late ack for an unknown reel", async () => {
    rows.push({ id: "r1", status: "unknown", ack_status: "timeout" });
    await ack(makeEnv(), { reel_id: "r1", status: "ok", ig_media_id: "ig1" });

    expect(rows[0].status).toBe("published");
    expect(rows[0].ack_status).toBe("ok");
  });
});
