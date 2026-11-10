export interface Env {
  SUPABASE_URL: string;
  SUPABASE_SERVICE_KEY: string;
  TOKENS: KVNamespace;
  FACTORY_API_KEY: string;
  FACTORY_HMAC_SECRET: string;
  MAKE_KEY: string;
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_CHAT_ID: string;
  META_APP_ID: string;
  META_APP_SECRET: string;
  IG_USER_ID: string;
  IG_ACCESS_TOKEN?: string;
  ASSETS: Fetcher;
  YOUTUBE_CLIENT_ID?: string;
  YOUTUBE_CLIENT_SECRET?: string;
  YOUTUBE_REFRESH_TOKEN?: string;
  YOUTUBE_ENABLED?: string;      // "true" only when YouTube delegation is approved
  // Make.com state-machine tuning (mirrors config.yaml publish.make; env wins).
  MAKE_CLAIM_WINDOW_MINUTES?: string;
  MAKE_UNACKED_ALERT_MINUTES?: string;
  MAKE_DEADMAN_MINUTES?: string;
  MAKE_CREDITS_BUDGET_MONTHLY?: string;
  MAKE_CREDITS_PER_RUN?: string;
  MAKE_MAX_CALLS_PER_MINUTE?: string;
  MAKE_BATCH_LIMIT?: string;
  // Feature flags (config.yaml is not shipped to the Worker, so these mirror it).
  // Defaults are deliberately conservative: direct Graph publishing is OFF.
  PUBLISH_BACKEND?: string;      // "make_com" (default) | "business_suite_manual" | "graph_api"
  ENGAGEMENT_ENABLED?: string;   // "true" only when engagement replies/DMs are approved
}

export async function sb(env: Env, path: string, init?: RequestInit) {
  const url = env.SUPABASE_URL.replace(/\/$/, "") + "/rest/v1" + path;
  const headers = {
    "apikey": env.SUPABASE_SERVICE_KEY,
    "Authorization": "Bearer " + env.SUPABASE_SERVICE_KEY,
    "Content-Type": "application/json",
    ...(init?.headers || {}),
  };
  return fetch(url, { ...init, headers });
}

export async function sbRpc(env: Env, fn: string, body: any) {
  const url = env.SUPABASE_URL.replace(/\/$/, "") + "/rest/v1/rpc/" + fn;
  return fetch(url, {
    method: "POST",
    headers: {
      "apikey": env.SUPABASE_SERVICE_KEY,
      "Authorization": "Bearer " + env.SUPABASE_SERVICE_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

/** Read a boolean-ish relay_state key, falling back to a default when missing/unreadable. */
export async function stateFlag(env: Env, key: string, def: boolean): Promise<boolean> {
  try {
    const r = await sb(env, `/relay_state?key=eq.${encodeURIComponent(key)}&select=value`);
    const rows = r.ok ? (await r.json()) as any[] : [];
    if (!rows.length) return def;
    const v = rows[0].value;
    if (typeof v === "boolean") return v;
    if (typeof v === "string") return v.toLowerCase() === "true";
    if (v && typeof v === "object" && "enabled" in v) return !!v.enabled;
    return def;
  } catch {
    return def;
  }
}

/** Read a string-ish relay_state key (e.g. publish_backend), falling back to a default. */
export async function stateString(env: Env, key: string, def: string): Promise<string> {
  try {
    const r = await sb(env, `/relay_state?key=eq.${encodeURIComponent(key)}&select=value`);
    const rows = r.ok ? (await r.json()) as any[] : [];
    if (!rows.length) return def;
    const v = rows[0].value;
    if (typeof v === "string") return v;
    if (v && typeof v === "object" && typeof v.value === "string") return v.value;
    return def;
  } catch {
    return def;
  }
}