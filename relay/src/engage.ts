import { Env, sb } from "./db";
import { now } from "./clock";
import { getToken } from "./tokens";

const KEYWORDS = ["CHALISA", "PDF", "AUDIO"];

export async function stepEngage(env: Env): Promise<void> {
  // poll comments for media <=72h
  const since = new Date(Date.now() - 72 * 3600000).toISOString();
  const media = await sb(env, `/relay_queue?status=eq.published&published_at=gte.${since}&select=ig_media_id`);
  const rows = media.ok ? await media.json() as any : [];
  for (const m of rows) {
    if (!m.ig_media_id) continue;
    const token = await getToken(env);
    const r = await fetch(`https://graph.instagram.com/v21.0/${m.ig_media_id}/comments?access_token=${token}`);
    const j: any = await r.json();
    const comments = j.data || [];
    for (const c of comments) {
      // upsert comment
      await sb(env, "/relay_comments", {
        method: "POST",
        headers: { "Prefer": "resolution=ignore-duplicates" },
        body: JSON.stringify({
          ig_comment_id: c.id,
          media_id: m.ig_media_id,
          username: c.username,
          text: c.text,
          received_at: now().toISOString(),
          status: "new",
        }),
      });
    }
  }
  // send due replies (scheduled)
  const due = await sb(env, `/relay_comments?status=eq.reply_scheduled&reply_after=lte.${now().toISOString()}&limit=5`);
  const dueRows = due.ok ? await due.json() as any : [];
  for (const c of dueRows) {
    const token = await getToken(env);
    await fetch(`https://graph.instagram.com/v21.0/${c.ig_comment_id}/replies`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ message: c.reply_text || "Har Har Mahadev!", access_token: token! }),
    });
    await sb(env, `/relay_comments?ig_comment_id=eq.${c.ig_comment_id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "replied", replied_at: now().toISOString() }),
    });
  }
  // keyword DMs
  const newComments = await sb(env, `/relay_comments?status=eq.new&limit=10`);
  const nc = newComments.ok ? await newComments.json() as any : [];
  for (const c of nc) {
    const upper = (c.text || "").toUpperCase();
    const kw = KEYWORDS.find(k => upper.includes(k));
    if (kw) {
      const token = await getToken(env);
      await fetch(`https://graph.instagram.com/v21.0/${env.IG_USER_ID}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipient: { comment_id: c.ig_comment_id },
          message: { text: "Here is the link: " + (env as any).WORKER_URL + "/chalisa" },
          access_token: token,
        }),
      });
      await sb(env, `/relay_comments?ig_comment_id=eq.${c.ig_comment_id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "dm_sent" }),
      });
    } else {
      // schedule a reply
      const delay = 45 + Math.floor(Math.random() * 375);
      const replyAfter = new Date(Date.now() + delay * 1000).toISOString();
      await sb(env, `/relay_comments?ig_comment_id=eq.${c.ig_comment_id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "reply_scheduled", reply_after: replyAfter, reply_text: "Har Har Mahadev! 🙏" }),
      });
    }
  }
}