import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { stepYoutube, YOUTUBE_DAILY_LIMIT } from "../src/youtube";

type Row = {
  id: string;
  status: string;
  yt_video_id: string | null;
  yt_status: string | null;
  published_at: string;
};

let queue: Row[];
let state: Record<string, any>;
let requests: string[];
let patches: string[];

function makeEnv(over: Record<string, any> = {}) {
  return {
    SUPABASE_URL: "https://sb.test",
    SUPABASE_SERVICE_KEY: "k",
    TOKENS: { get: async () => null, put: async () => {} },
    ...over,
  } as any;
}

const today = () => new Date().toISOString().slice(0, 10);

beforeEach(() => {
  queue = [
    { id: "r1", status: "published", yt_video_id: null, yt_status: null, published_at: "2026-01-01T00:00:00Z" },
  ];
  state = {};
  requests = [];
  patches = [];

  vi.stubGlobal("fetch", vi.fn(async (input: any, init?: any) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    requests.push(`${method} ${url.pathname}${url.search}`);

    if (url.pathname === "/rest/v1/relay_state") {
      if (method === "POST") {
        const body = JSON.parse(init.body);
        state[body.key] = body.value;
        return new Response(null, { status: 201 });
      }
      const key = url.searchParams.get("key")?.replace(/^eq\./, "") ?? "";
      const value = state[key];
      return new Response(JSON.stringify(value === undefined ? [] : [{ key, value }]), { status: 200 });
    }

    if (url.pathname === "/rest/v1/relay_queue") {
      if (method === "PATCH") {
        patches.push(url.search);
        const id = url.searchParams.get("id")?.replace(/^eq\./, "");
        const row = queue.find(r => r.id === id && r.yt_status === null);
        if (!row) return new Response("[]", { status: 200 });
        row.yt_status = JSON.parse(init.body).yt_status;
        return new Response(null, { status: 204 });
      }
      const rows = queue.filter(
        r =>
          r.status === "published" &&
          r.yt_video_id === null &&
          r.yt_status === null &&
          url.searchParams.get("yt_status") === "is.null",
      );
      return new Response(JSON.stringify(rows), { status: 200 });
    }

    return new Response("{}", { status: 200 });
  }));
});

afterEach(() => { vi.unstubAllGlobals(); });

describe("youtube delegation", () => {
  it("does nothing unless YOUTUBE_ENABLED=true", async () => {
    await stepYoutube(makeEnv({ YOUTUBE_REFRESH_TOKEN: "tok" }));
    expect(requests).toEqual([]);
  });

  it("does nothing without a refresh token", async () => {
    await stepYoutube(makeEnv({ YOUTUBE_ENABLED: "true" }));
    expect(requests).toEqual([]);
  });

  it("delegates a published reel once and records the daily meter", async () => {
    await stepYoutube(makeEnv({ YOUTUBE_ENABLED: "true", YOUTUBE_REFRESH_TOKEN: "tok" }));

    expect(requests.some(r => r.includes("yt_status=is.null"))).toBe(true);
    expect(patches).toHaveLength(1);
    expect(queue[0].yt_status).toBe("delegated_to_factory");
    expect(state.yt_steps_day).toEqual({ day: today(), count: 1 });
  });

  it("does not re-mark the same reel on the next tick", async () => {
    const env = makeEnv({ YOUTUBE_ENABLED: "true", YOUTUBE_REFRESH_TOKEN: "tok" });
    await stepYoutube(env);
    await stepYoutube(env);

    expect(patches).toHaveLength(1);
    expect(state.yt_steps_day.count).toBe(1);
  });

  it("stops at the daily delegation limit", async () => {
    state.yt_steps_day = { day: today(), count: YOUTUBE_DAILY_LIMIT };
    await stepYoutube(makeEnv({ YOUTUBE_ENABLED: "true", YOUTUBE_REFRESH_TOKEN: "tok" }));

    expect(patches).toHaveLength(0);
    expect(requests.some(r => r.includes("relay_queue"))).toBe(false);
  });

  it("resets the meter when the stored day is stale", async () => {
    state.yt_steps_day = { day: "1999-01-01", count: YOUTUBE_DAILY_LIMIT };
    await stepYoutube(makeEnv({ YOUTUBE_ENABLED: "true", YOUTUBE_REFRESH_TOKEN: "tok" }));

    expect(patches).toHaveLength(1);
    expect(state.yt_steps_day).toEqual({ day: today(), count: 1 });
  });
});
