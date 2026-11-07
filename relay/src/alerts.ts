import { Env } from "./db";

export async function telegram(env: Env, text: string) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) return;
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text }),
  });
}

export async function dedupeAlert(env: Env, key: string, text: string) {
  const state = await env.TOKENS.get("alerts_sent");
  const sent = state ? JSON.parse(state) : {};
  if (sent[key]) return false;
  sent[key] = Date.now();
  await env.TOKENS.put("alerts_sent", JSON.stringify(sent));
  await telegram(env, text);
  return true;
}