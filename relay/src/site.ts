import { Env, sb } from "./db";

export async function handleSite(env: Env, request: Request, path: string): Promise<Response> {
  if (path === "/status.json") {
    const r = await sb(env, "/relay_queue?select=status");
    const rows = r.ok ? await r.json() as any : [];
    const counts: Record<string, number> = {};
    for (const x of rows) counts[x.status] = (counts[x.status] || 0) + 1;
    return new Response(JSON.stringify({ counts, ts: new Date().toISOString() }), {
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
    });
  }
  if (path === "/api/dashboard") {
    // Buffer health
    const qBuf = await sb(env, "/relay_queue?select=status,uuid,series_day,format,scheduled_at,remote_video_url,youtube_video_id,youtube_permalink");
    const rows = qBuf.ok ? await qBuf.json() as any[] : [];
    const counts: Record<string, number> = {};
    for (const x of rows) counts[x.status] = (counts[x.status] || 0) + 1;
    let bufferFloor = 5;
    let rendered = counts["rendered"] || 0;
    let planned = counts["planned"] || 0;
    // Local snapshot pushed by the laptop daemon: the single source of truth for
    // buffer health, because local SQLite is where renders actually live.
    const qSnap = await sb(env, "/relay_state?key=eq.buffer_snapshot&select=value");
    const snapRows = qSnap.ok ? await qSnap.json() as any[] : [];
    const snapshot: any = snapRows.length ? snapRows[0].value : null;
    if (snapshot && typeof snapshot === "object") {
      bufferFloor = Number(snapshot.floor) || bufferFloor;
      rendered = Number(snapshot.rendered) || 0;
      planned = Number(snapshot.planned) || 0;
    }
    // Daemon heartbeat
    const qHb = await sb(env, "/relay_state?key=eq.laptop_last_seen&select=value");
    const hbRows = qHb.ok ? await qHb.json() as any[] : [];
    const lastSeen = hbRows.length ? (hbRows[0].value?.ts || null) : null;
    // Publishing ledger (uploaded/published)
    const published = rows.filter((r: any) => r.status === "uploaded" || r.status === "published")
      .slice(0, 20)
      .map((r: any) => ({
        uuid: r.uuid,
        series_day: r.series_day,
        format: r.format,
        scheduled_at: r.scheduled_at,
        video_url: r.remote_video_url,
        youtube_video_id: r.youtube_video_id,
        youtube_permalink: r.youtube_permalink,
      }));
    // Strategy insights from relay_state
    const qStrat = await sb(env, "/relay_state?key=in.(weights,prompt_notes,weekly_report,pending_approval_list,approved_reels)&select=key,value");
    const stratRows = qStrat.ok ? await qStrat.json() as any[] : [];
    const strategy: Record<string, any> = {};
    for (const x of stratRows) strategy[x.key] = x.value;
    // pending approval list
    let pending: any[] = [];
    const pal = stratRows.find((x: any) => x.key === "pending_approval_list");
    if (pal && Array.isArray(pal.value)) pending = pal.value;
    else if (pal && typeof pal.value === "string") { try { pending = JSON.parse(pal.value); } catch {} }
    // Supabase connection health
    let supabase_ok = false;
    try { const r = await sb(env, "/relay_state?limit=1"); supabase_ok = r.ok; } catch { supabase_ok = false; }
    const payload = {
      ts: new Date().toISOString(),
      buffer: {
        floor: bufferFloor,
        rendered,
        planned,
        total: snapshot && snapshot.by_status
          ? Object.values(snapshot.by_status as Record<string, number>).reduce((a, b) => a + Number(b || 0), 0)
          : rows.length,
        healthy: rendered >= bufferFloor,
        by_status: snapshot && snapshot.by_status ? snapshot.by_status : counts,
        source: snapshot ? "laptop" : "relay_queue",
        snapshot: snapshot || null,
      },
      daemon: {
        last_seen: lastSeen,
        online: lastSeen ? (Date.now() - new Date(lastSeen).getTime()) < 30 * 60 * 1000 : false,
      },
      system: {
        supabase_ok,
        counts,
      },
      publishing: published,
      pending_approval: pending,
      strategy,
    };
    return new Response(JSON.stringify(payload), {
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
    });
  }
  if (path === "/api/analytics") {
    // Preferred source: the laptop pushes a fresh snapshot (it holds the OAuth creds).
    const url = new URL(request.url);
    const fresh = url.searchParams.get("fresh") === "1";
    if (!fresh) {
      try {
        const qs = await sb(env, "/relay_state?key=eq.analytics_snapshot&select=value");
        const srows = qs.ok ? await qs.json() as any[] : [];
        if (srows.length) {
          const v = srows[0].value;
          if (v && typeof v === "object") {
            const ageMin = (Date.now() - new Date(v.ts || 0).getTime()) / 60000;
            if (ageMin < 60) {
              return new Response(JSON.stringify({
                ...v,
                youtube_auth: true,
                instagram: instagramBlock(env),
                source: "laptop-snapshot",
              }), {
                headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*", "X-Cache": "laptop" },
              });
            }
          }
        }
      } catch {}
    }
    // YouTube quota guard: the dashboard polls every 15s, so cache results in KV.
    if (!fresh) {
      try {
        const cached = await env.TOKENS.get("analytics_cache");
        if (cached) {
          return new Response(cached, {
            headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*", "X-Cache": "hit" },
          });
        }
      } catch {}
    }
    // 1) reels the relay queue already knows about
    const q = await sb(env, "/relay_queue?select=reel_id,series_day,format,remote_video_url,youtube_video_id,youtube_permalink,status&status=eq.uploaded");
    const rows = q.ok ? await q.json() as any[] : [];
    // 2) manually published reels recorded in relay_state.published_ledger
    let ledger: any[] = [];
    try {
      const ql = await sb(env, "/relay_state?key=eq.published_ledger&select=value");
      const lrows = ql.ok ? await ql.json() as any[] : [];
      if (lrows.length) {
        const v = lrows[0].value;
        if (Array.isArray(v)) ledger = v;
        else if (typeof v === "string") { try { ledger = JSON.parse(v); } catch {} }
      }
    } catch { ledger = []; }
    const entries: any[] = [];
    for (const r of rows) {
      entries.push({
        reel_id: r.reel_id, series_day: r.series_day, format: r.format,
        youtube_video_id: r.youtube_video_id, youtube_permalink: r.youtube_permalink,
        platform: "youtube", source: "relay_queue",
      });
    }
    for (const l of ledger) {
      if (!l || !l.youtube_video_id) continue;
      if (entries.some((e) => e.youtube_video_id === l.youtube_video_id)) continue;
      entries.push({
        reel_id: l.reel_id || l.youtube_video_id,
        series_day: l.series_day ?? null,
        format: l.format ?? null,
        youtube_video_id: l.youtube_video_id,
        youtube_permalink: l.youtube_permalink || ("https://youtube.com/shorts/" + l.youtube_video_id),
        platform: "youtube", source: "ledger",
      });
    }
    // one OAuth token for every video lookup
    let token = "";
    const cid = env.YOUTUBE_CLIENT_ID, csec = env.YOUTUBE_CLIENT_SECRET, rt = env.YOUTUBE_REFRESH_TOKEN;
    if (cid && csec && rt) {
      try {
        const tr = await fetch("https://oauth2.googleapis.com/token", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: `client_id=${encodeURIComponent(cid)}&client_secret=${encodeURIComponent(csec)}&refresh_token=${encodeURIComponent(rt)}&grant_type=refresh_token`,
        });
        if (tr.ok) token = (await tr.json() as any).access_token || "";
      } catch { token = ""; }
    }
    const items = await Promise.all(entries.slice(0, 20).map(async (e) => {
      let stats: any = null;
      if (token && e.youtube_video_id) {
        try {
          const sr = await fetch(
            `https://www.googleapis.com/youtube/v3/videos?part=statistics,contentDetails,snippet&id=${encodeURIComponent(e.youtube_video_id)}`,
            { headers: { Authorization: `Bearer ${token}` } });
          if (sr.ok) {
            const sj: any = await sr.json();
            const v = sj.items?.[0];
            if (v) {
              stats = { ...v.statistics, title: v.snippet?.title, published_at: v.snippet?.publishedAt, duration: v.contentDetails?.duration };
            }
          }
        } catch { stats = null; }
      }
      return { ...e, stats };
    }));
    const ig = instagramBlock(env);
    const payload = JSON.stringify({
      ts: new Date().toISOString(),
      youtube_auth: !!token,
      items,
      instagram: ig,
      totals: {
        views: items.reduce((n, i) => n + Number(i.stats?.viewCount || 0), 0),
        likes: items.reduce((n, i) => n + Number(i.stats?.likeCount || 0), 0),
        comments: items.reduce((n, i) => n + Number(i.stats?.commentCount || 0), 0),
      },
    });
    try { await env.TOKENS.put("analytics_cache", payload, { expirationTtl: 600 }); } catch {}
    return new Response(payload, {
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*", "X-Cache": "miss" },
    });
  }
  if (path === "/mediakit") {
    return new Response("<h1>Media Kit</h1><p>Activated at 5k followers.</p>", { headers: { "Content-Type": "text/html" } });
  }
  // static assets
  return env.ASSETS.fetch(request);
}

function instagramBlock(env: Env) {
  return {
    configured: !!(env.IG_ACCESS_TOKEN && env.IG_USER_ID),
    posting_enabled: false,
    items: [] as any[],
    note: "Instagram publishing is OFF (H3). Metrics appear here once posting is enabled.",
  };
}
