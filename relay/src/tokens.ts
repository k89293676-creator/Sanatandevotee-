import { Env } from "./db";
import { now } from "./clock";

const KEY = "ig_access_token";
const EXP = "ig_token_expiry";

export async function getToken(env: Env): Promise<string | null> {
  return env.TOKENS.get(KEY);
}

export async function setToken(env: Env, token: string, expiryMs: number) {
  await env.TOKENS.put(KEY, token);
  await env.TOKENS.put(EXP, String(expiryMs));
}

export async function tokenDaysLeft(env: Env): Promise<number> {
  const e = await env.TOKENS.get(EXP);
  if (!e) return 0;
  return Math.floor((Number(e) - now().getTime()) / 86400000);
}

export async function refreshIfNeeded(env: Env): Promise<{ refreshed: boolean; error?: string }> {
  // refresh every 30 days; token must be >=24h old and unexpired
  const exp = await env.TOKENS.get(EXP);
  const token = await env.TOKENS.get(KEY);
  if (!token || !exp) return { refreshed: false, error: "missing" };
  const daysLeft = (Number(exp) - now().getTime()) / 86400000;
  if (daysLeft > 25) return { refreshed: false };
  // call refresh endpoint (Instagram Login long-lived refresh)
  const url = `https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=${token}`;
  const r = await fetch(url);
  if (!r.ok) return { refreshed: false, error: `http ${r.status}` };
  const j: any = await r.json();
  const newToken = j.access_token;
  const expiresIn = j.expires_in || 5184000;
  await setToken(env, newToken, now().getTime() + expiresIn * 1000);
  return { refreshed: true };
}