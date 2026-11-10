# Found Issues (out of scope for this session; do not auto-fix)

- `content_engine.generate_script` computes a judge scorecard but never persists it through `script_store.save_script` for the batch path (`scripts/generate_all.py`); only the daemon path saves.
- `planner.special_days` now computes real tithi for Shivratri/Kartik Purnima and Mahashivratri, but other festivals (Navratri, Diwali, etc.) are not yet generated; `_note` labels approximations.
- `optimizer` reward/floor/cap logic exists but is not wired into `planner.choose_arm` beyond `choose_arm`; reward updates are only called from the daemon path.
- `pdfgen` and `monetisation` modules are unreviewed stubs.
- `youtube_auth` / `youtube_upload` are exercised end-to-end (real publish of Day 1, `gJBHA7cb4H0`; channel branding applied via API). Still outside the API: channel name, avatar, About links and handle can only be set in YouTube Studio, and custom thumbnails need phone-verified channel status.
- `relay/public` has no `chalisa` page even though `index.ts` routes `/chalisa` to ASSETS, so that path returns 404; the channel's About link points at `/` instead.
- `analytics.import_insights_csv`, `youtube_stats`, `weekly_report` are partial.
- `lessons_memo` exists but is not wired into the daemon.
- `osx/` generators target macOS; untested on Windows.
- `simulate_offline.py` only calls vitest, not the Python pipeline.
- `audio_mix_graph` sidechain assumes the bed is stereo after `aresample`; the procedural bed is mono and gets upmixed. Verify in Heavy Pass.
- `edge-tts` rarely emits `SentenceBoundary`; cut snapping depends on `sentence_starts_from`, which is unverified against real boundary text.
- `gather_shots` video clips are downloaded at source resolution and only resized in ffmpeg; large clips can inflate work-dir size.
- `validate()` runs ffprobe/ffmpeg filters that take ~10s; scoring calls it once per render.
- `/api/factory/approve` is intentionally unauthenticated so the browser dashboard button can call it. It is guarded: the uuid must already be present in `relay_state.pending_approval_list`, so it cannot approve arbitrary/unknown reels. Residual risk: anyone who learns a queued reel_id could approve that pending reel. Acceptable while H2 is a human review gate, but should be HMAC-signed if the dashboard ever moves off a trusted origin.
- The Cloudflare Worker has no YouTube OAuth credentials (`yt_oauth_complete:false`), so `/api/analytics` prefers the laptop-pushed `relay_state.analytics_snapshot` (the laptop is the only place with the creds). The snapshot is only refreshed when the daemon ticks, so stats can be up to one tick (~15 min) stale. Instagram analytics are intentionally empty until H3 enables posting.
- Bulk script generation (`scriptgen.run` over the whole missing corpus) is now gated behind `ALLOW_HEAVY=1` in `daemon.catch_up`; otherwise it only tops up a few scripts via `script_store.ensure_min_scripts`. Generating ~77 scripts on the Groq free tier previously blocked the daemon from ever reaching `tick()`.
- `render_reel` still hard-fails when, after the 1.08x speed-up, narration exceeds the 58s cap (e.g. reel `06742cc3`, 67.9s). The planner does not pre-filter scripted reels by measured TTS duration, so a few long scripts burn up to 3 render attempts before being marked `failed`. Needs a planned-duration-aware picker (or sentence-boundary truncation) — deferred because it touches devotional text.