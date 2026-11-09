import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { scheduled } from "../src/scheduled";

let state: Record<string, any> = {};
let calls: string[] = [];

function makeEnv() {
  const kv = new Map<string, string>();
  return {
    SUPABASE_URL: "https://sb.test",
    SUPABASE_SERVICE_KEY: "k",
    TOKENS: {
      get: async (k: string) => kv.get(k) ?? null,
      put: async (k: string, v: string) => { kv.set(k, v); },
    },
    TELEGRAM_BOT_TOKEN: "",
    TELEGRAM_CHAT_ID: "",
  } as any;
}

beforeEach(() => {
  state = {};
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (input: any, init?: any) => {
    const url = String(input);
    calls.push(url + " " + (init?.method ?? "GET"));
    if (url.includes("/rest/v1/relay_state?key=eq.")) {
      const key = decodeURIComponent(url.split("key=eq.")[1].split("&")[0]);
      const value = state[key];
      return new Response(JSON.stringify(value === undefined ? [] : [{ key, value }]), { status: 200 });
    }
    if (url.includes("/rest/v1/relay_queue")) return new Response("[]", { status: 200 });
    if (url.includes("/rest/v1/rpc/")) return new Response("{}", { status: 200 });
    return new Response("{}", { status: 200 });
  }));
});

afterEach(() => { vi.unstubAllGlobals(); });

const used = (needle: string) => calls.some(c => c.includes(needle));

describe("scheduled feature flags", () => {
  it("does not run the Graph publisher with the default (make_com) backend", async () => {
    await scheduled(makeEnv(), {} as any);
    expect(used("/rpc/claim_due_reel")).toBe(false);
    expect(used("graph.instagram.com")).toBe(false);
  });

  it("does not run the Graph publisher when posting_enabled is false", async () => {
    state = { publish_backend: "graph_api", posting_enabled: false };
    await scheduled(makeEnv(), {} as any);
    expect(used("/rpc/claim_due_reel")).toBe(false);
    expect(used("graph.instagram.com")).toBe(false);
  });

  it("runs the publisher only when backend=graph_api and posting is enabled", async () => {
    state = { publish_backend: "graph_api", posting_enabled: true };
    await scheduled(makeEnv(), {} as any);
    expect(used("/rpc/claim_due_reel")).toBe(true);
  });

  it("does not poll engagement unless engagement is enabled", async () => {
    state = { publish_backend: "graph_api", posting_enabled: true, engagement_enabled: false };
    await scheduled(makeEnv(), {} as any);
    expect(used("/relay_comments")).toBe(false);
  });

  it("polls engagement when explicitly enabled", async () => {
    state = { publish_backend: "graph_api", posting_enabled: true, engagement_enabled: true };
    await scheduled(makeEnv(), {} as any);
    expect(used("relay_comments")).toBe(true);
  });
});
