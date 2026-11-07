import { Env, sb } from "./db";

export async function handleSite(env: Env, request: Request, path: string): Promise<Response> {
  if (path === "/status.json") {
    const r = await sb(env, "/relay_queue?select=status");
    const rows = r.ok ? await r.json() as any : [];
    const counts: Record<string, number> = {};
    for (const x of rows) counts[x.status] = (counts[x.status] || 0) + 1;
    return new Response(JSON.stringify({ counts, ts: new Date().toISOString() }), {
      headers: { "Content-Type": "application/json" },
    });
  }
  if (path === "/mediakit") {
    return new Response("<h1>Media Kit</h1><p>Activated at 5k followers.</p>", { headers: { "Content-Type": "text/html" } });
  }
  // static assets
  return env.ASSETS.fetch(request);
}