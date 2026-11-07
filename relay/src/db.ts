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
  ASSETS: Fetcher;
  YOUTUBE_CLIENT_ID?: string;
  YOUTUBE_CLIENT_SECRET?: string;
  YOUTUBE_REFRESH_TOKEN?: string;
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