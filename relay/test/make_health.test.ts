import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { checkMakeHealth } from "../src/make_health";

type Row = {
  id: string;
  status: string;
  ack_status?: string | null;
  handed_off_at?: string | null;
  last_error?: string | null;
};

let rows: Row[];
let state: Record<string, any>;
let alerts: string[];
let kv: Map<string, string>;

function makeEnv(over: Record<string, any> = {}) {
  return {
    SUPABASE_URL: "https://sb.test",
    SUPABASE_SERVICE_KEY: "k",
    TELEGRAM_BOT_TOKEN: "tok",
    TELEGRAM_CHAT_ID: "chat",
    TOKENS: {
      get: async (k: string) => kv.get(k) ?? null,
      put: async (k: string, v: string) => { kv.set(k, v); },
    },
    ...over,
  } as any;
}

const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();

beforeEach(() => {
  rows = [];
  state = {};
  alerts = [];
  kv = new Map();

  vi.stubGlobal("fetch", vi.fn(async (input: any, init?: any) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const sp = url.searchParams;

    if (url.hostname === "api.telegram.org") {
      alerts.push(JSON.parse(init.body).text);
      return new Response("{}", { status: 200 });
    }

    if (url.pathname === "/rest/v1/relay_state") {
      const key = (sp.get("key") ?? "").replace(/^eq\./, "");
      const value = state[key];
      return new Response(JSON.stringify(value === undefined ? [] : [{ key, value }]), { status: 200 });
    }

    if (url.pathname === "/rest/v1/relay_queue") {
      const statusEq = (sp.get("status") ?? "").replace(/^eq\./, "");
      const ackNull = sp.get("ack_status") === "is.null";
      const matched = rows.filter(r =>
        (!statusEq || r.status === statusEq) &&
        (!ackNull || r.ack_status === null || r.ack_status === undefined),
      );
      if (method === "PATCH") {
        const body = JSON.parse(init.body);
        for (const r of matched) Object.assign(r, body);
        return new Response(null, { status: 204 });
      }
      return new Response(JSON.stringify(matched), { status: 200 });
    }

    return new Response("{}", { status: 200 });
  }));
});

afterEach(() => { vi.unstubAllGlobals(); });

describe("make health", () => {
  it("is healthy when Make pinged recently", async () => {
    state.make_last_call = { ts: minutesAgo(2) };
    const h = await checkMakeHealth(makeEnv());
    expect(h.dead).toBe(false);
    expect(alerts).toEqual([]);
  });

  it("alerts once when Make stops pinging", async () => {
    state.make_last_call = { ts: minutesAgo(120) };
    const env = makeEnv();
    const h1 = await checkMakeHealth(env);
    const h2 = await checkMakeHealth(env);

    expect(h1.dead).toBe(true);
    expect(h2.dead).toBe(true);
    expect(alerts.filter(a => a.includes("dead-man"))).toHaveLength(1);
  });

  it("reminds about an unacked handoff without changing its state", async () => {
    rows.push({ id: "r1", status: "handed_off", ack_status: null, handed_off_at: minutesAgo(40) });
    state.make_last_call = { ts: minutesAgo(1) };
    const h = await checkMakeHealth(makeEnv());

    expect(h.unacked).toBe(1);
    expect(rows[0].status).toBe("handed_off");
    expect(alerts.some(a => a.includes("still not acked"))).toBe(true);
  });

  it("marks a handoff unknown after the dead-man deadline", async () => {
    rows.push({ id: "r1", status: "handed_off", ack_status: null, handed_off_at: minutesAgo(90) });
    state.make_last_call = { ts: minutesAgo(1) };
    await checkMakeHealth(makeEnv());

    expect(rows[0].status).toBe("unknown");
    expect(rows[0].ack_status).toBe("timeout");
    expect(rows[0].last_error).toContain("90");
  });

  it("treats a missing handed_off_at as overdue", async () => {
    rows.push({ id: "r1", status: "handed_off", ack_status: null, handed_off_at: null });
    state.make_last_call = { ts: minutesAgo(1) };
    await checkMakeHealth(makeEnv());
    expect(rows[0].status).toBe("unknown");
  });
});
