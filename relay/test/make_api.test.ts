import { describe, it, expect } from "vitest";
import { handleMakeApi } from "../src/make_api";

describe("make_api auth", () => {
  it("returns 404 for bad bearer", async () => {
    const env: any = { MAKE_KEY: "mk_test123456789012345678901234567890", SUPABASE_URL: "https://x.supabase.co", SUPABASE_SERVICE_KEY: "k", TOKENS: { get: async () => null, put: async () => {} } };
    const req = new Request("https://x/api/make/ping?test=1", { headers: { Authorization: "Bearer wrong" } });
    const res = await handleMakeApi(env, req, "/api/make/ping");
    expect(res.status).toBe(404);
  });
});