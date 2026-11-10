# Shiv Chalisa Reel Pipeline — Project Report

**Generated:** 2026-11-10
**Repo:** `C:\Users\lenovo\chalisa` (git, branch main)
**Latest commits:** `249e1af` (channel branding), `7d1c145` (YouTube tags/day-1), `dacb788` (ignore client_secret)
**This round (uncommitted at time of writing):** control-center dashboard fixes (real video previews, live analytics, laptop buffer snapshot), H2 approval round-trip, local analytics ledger, daemon `catch_up` no longer blocks on bulk scriptgen.

---

## 1. What this project is

An **autonomous, $0-cost pipeline** that produces and publishes 2 short-form (Instagram Reels / YouTube Shorts) videos per day for the devotional series **"Shiv Chalisa"** (42 verses → ~42 days of content). It runs on a Lenovo A10-9600P laptop (4 cores, ~2.8 GB free RAM, integrated GPU) and a Cloudflare Worker + Supabase + Make.com relay. Everything is free-tier only.

Two halves:
- **Factory (Python)** — verse → script → TTS → render (ffmpeg) → upload to relay.
- **Relay (Cloudflare Worker + Supabase + Make.com)** — queues, scheduling, publishing to YouTube/Instagram, analytics, engagement.

Brand: YouTube channel **"Shiv Chalisa 43"** (`@shivchalisa43`, `UCaEn2677hRCSh03kbhy2kqg`), relay `https://chalisa-relay.mew92724.workers.dev`.

---

## 2. Core architecture

```
verses.json (42 units)
  → scriptgen (Groq LLM, pydantic, safety filter)
  → planner (slot A/B, special days, optimizer arms)
  → TTS (edge-tts/gTTS/Piper, word boundaries)
  → captions (ASS, 3 timing methods)
  → render (ffmpeg: Ken Burns crop-pan, xfade, libass, two-pass loudnorm, phash dedupe)
  → sync (HMAC upload-url to Supabase Storage)
  → relay DB (relay_queue, status)
  → daemon tick (power-gated) renders + uploads
  → Make.com claims reels (claim_due_reel) and posts to YouTube/IG
  → analytics/engagement feedback loop
```

Hardware policy: `render workers=1`, `max_threads=2`, `-preset veryfast`, render window 01:00–06:00 IST, `power.can_render` requires AC + ≥3 GB free RAM + CPU<40% + not working hours, daily render-minute cap. Heavy work gated behind `ALLOW_HEAVY=1`.

---

## 3. Factory (Python) — module status

Source: `src/factory/` (33 modules). Status legend: REAL / PARTIAL / STUB.

| Module | Status | Notes |
|---|---|---|
| config.py | REAL | load_config, paths |
| db.py | REAL | SQLite WAL, 13 tables |
| secrets_store.py | REAL | keyring + env-var fallback |
| logging_setup.py | REAL | redaction (9 patterns) |
| notify.py | REAL | Telegram send |
| verses.py | REAL | load/upsert/get |
| scriptgen.py | REAL | Groq primary, pydantic, safety filter |
| content_engine.py | PARTIAL | multi-pass + judge; judge hard-coded 80/60; not wired to generation |
| planner.py | PARTIAL | slot logic works; special days partial; optimizer not wired |
| optimizer.py | PARTIAL | ensure_arms, weights; no reward/floor/cap wired to planner |
| tts.py | REAL | edge-tts/gTTS/Piper, Speech, synthesize_chunks, boundaries preserved |
| captions.py | REAL | chunking, 3 timing methods, build_ass |
| render.py | REAL | RenderSpec, manifest, validate, contact_sheet, quality_score, sentence-snapped cuts, varied transitions, sidechain ducking, phash dedupe |
| fonts.py | REAL | fontTools coverage check |
| visuals/ | PARTIAL→REAL | chain + providers (Pixabay/Wikimedia/Pollinations/procedural) + 8 strategies incl. mixed_montage default; strategies real |
| audio_bed.py | REAL | procedural bed, -28 dB, fade |
| sync.py | REAL | HMAC, upload-url, verify, enqueue |
| power.py | REAL | battery/AC, can_render, max_threads |
| daemon.py | REAL | msvcrt lock + real tick (renders + uploads), power-gated |
| pdfgen.py | STUB | unreviewed |
| monetisation.py | STUB | unreviewed |
| analytics.py | REAL | CSV import, YouTube stats, local `data/published_ledger.json`, `push_analytics` snapshot to relay |
| lessons_memo.py | PARTIAL | exists, wired into daemon (soft guidance only) |
| knowledge.py | PARTIAL | fetch_card exists, not run |
| quality_score.py | PARTIAL | exists, not wired to render manifest |
| osx/ | PARTIAL | generators exist, untested on Windows |
| phash.py | REAL | dHash + is_duplicate |
| jobs.py | REAL | build_spec, render_reel_row, mark_failed, upload_reel (+ Make webhook, cleanup) |
| llm/ (groq_client, rate_limiter, templates) | REAL | Groq client, rate limiter, templates |

Scripts (`scripts/`): 27 files. Key ones: `generate_all.py` (REAL), `render_one.py` (REAL), `render_batch.py` (REAL, ALLOW_HEAVY guard), `sync_now.py` (REAL), `verify_text.py` (REAL, never sets verified_flag), `special_days.py` (REAL approx, tithi via ephem), `check_sync.py` (REAL), `youtube_auth.py` (REAL OAuth, exercised), `youtube_post_day1.py` (Day-1 publish metadata), `channel_branding.py` / `channel_setup.py` (NEW — YouTube channel page setup), `doctor.py`, `secret_scan.py`, `run_all_checks.py`, `install.py` (PARTIAL), `simulate_offline.py` (STUB).

---

## 4. Relay (Cloudflare Worker) — status

Deployed at `https://chalisa-relay.mew92724.workers.dev`. Source: `relay/src/` (16 modules).

| Module | Status |
|---|---|
| index.ts | routes /api/factory/*, /api/make/*, site, /status.json, /mediakit, /chalisa, / |
| db.ts | Supabase queries + claim_due_reel |
| factory_api.ts | factory endpoints (upload-url, ensure-bucket, state-set, enqueue, state, heartbeat, weights, approved, approve, selfcheck); HMAC gate; `approve` is public but queue-guarded |
| make_api.ts | claim_due_reel, claimed→handed_off, credit gate, rate limit, idempotent ack |
| make_health.ts | unacked→unknown + dead-man alerts |
| scheduled.ts | cron triggers (* * * * *, 30 18 * * *) + recoverStuck |
| youtube.ts | YouTube Data API (gated by YOUTUBE_ENABLED) |
| publisher.ts | Make handoff |
| engage.ts | engagement (comment polling, replies) — gated |
| insights.ts | insights import |
| alerts.ts | Telegram alerts |
| tokens.ts | KV token store |
| site.ts | /status.json, /mediakit, pages, `/api/dashboard` (laptop buffer snapshot), `/api/analytics` (laptop snapshot + KV cache) |
| templates.ts, clock.ts | helpers |

Supabase: migrations 001–003 applied (`relay_queue`, `relay_comments`, `relay_insights`, `relay_account`, `relay_state`, `relay_events`, `claim_due_reel`). Migration `004_queue_resilience.sql` **not yet applied** (blocks `recoverStuck`/`relay_errors` in prod).

KV namespace `TOKENS` bound. Site pages: `/`, `/dashboard`, `/privacy`, `/terms`, `/data-deletion`, `/mediakit` = 200; `/chalisa` = 404 (no page in `relay/public`).

Control Center dashboard (`/dashboard`, `relay/public/dashboard.html`): daemon + Supabase health, buffer health from the laptop `buffer_snapshot`, an approval queue that renders a real `<video>` preview for each pending reel (Supabase Storage `media` bucket via `/api/factory/upload-url`), and a live YouTube analytics table (`/api/analytics`, prefers the laptop snapshot).

Tests: vitest **28 passed**; tsc clean.

---

## 5. Infrastructure & external services

| Service | Status |
|---|---|
| Cloudflare Worker | Deployed, selfcheck green |
| Supabase | Migrations 001–003 applied; 004 pending |
| Make.com | Slot A (06:30 IST) + Slot B (19:00 IST) scenarios built, **OFF** (H3 gate) |
| Telegram bot | Token + chat ID stored; "relay OK" sent |
| Groq LLM | Primary `qwen/qwen3.8-27b`, fallbacks `gpt-oss-20b`/`gpt-oss-120b`; daily budget 100k tokens |
| YouTube | OAuth exercised; Day 1 published; channel fully branded |
| Instagram | Not yet (Make handles posting) |
| GitHub Actions | `.github/workflows/render.yml` — 6-hourly cloud render + upload |

---

## 6. Human gates (user-only, never auto-passed)

- **H1** — verse text verification. ✅ **PASSED** (user granted H1; all 42 units `verified_flag=1`).
- **H2** — reel approval. Day 1 published (`gJBHA7cb4H0`). Day 2 reel `4ad5cb0d-483a-4188-8380-55fcb20185ba` is rendered, preview-uploaded and **waiting in the dashboard queue** for the user to click Approve.
- **H3** — Make scenarios ON (`posting_enabled`). Still OFF.

`posting_enabled=false` in `relay_state`. No scenario turned on. No `verified_flag` or `approved_at` set by code in this round.

---

## 7. Heavy verification status

Per compute policy: heavy work only with `ALLOW_HEAVY=1`, slow tests marked `@pytest.mark.heavy`.

Verified in Heavy Pass (2026-11-09):
- `test_render.py` — 3 passed (full render + validate, manifest shaping, validate-fails-for-right-reason). Full render took 318.59 s.
- Real reel via `jobs.render_reel_row` (meaning format, 36.4 s) — PASSED (340.4 s). 8/8 distinct assets, `cut_source=mixed`, transitions varied, `quality_score=100`, validate `ok=True`, LUFS -14.0.
- `render_batch.py --limit 1` — success + failure path PASSED.
- `simulate_offline.py` — PASSED (28 relay tests).

Pending heavy items: see `docs/HEAVY_QUEUE.md` (atempo duration guard, cleanup hooks, sidechain audibility, Pixabay live dedupe, sentence-snapped cuts vs real TTS, etc.).

---

## 8. YouTube channel setup — COMPLETE

Channel: **Shiv Chalisa 43** (`@shivchalisa43`, `UCaEn2677hRCSh03kbhy2kqg`).

| Item | Status | Evidence |
|---|---|---|
| Channel name | ✅ Set | API + public page |
| Handle | ✅ `@shivchalisa43` | API `customUrl` |
| Description (614 chars, Hindi+English, daily 6 AM, SHIVA CTA, playlist link) | ✅ Live | public channel HTML |
| Keywords (18 terms) | ✅ Live | API |
| Country `IN` / language `hi` | ✅ | API |
| Banner (2560×1440, copy in 1546×423 safe area) | ✅ Live | asset ID in public page |
| Avatar (800×800, gold ring + ॐ + 43) | ✅ Live | pixel-verified (dark navy corners, gold ring) |
| Trailer (non-subscribers) | ✅ Day 1 short `gJBHA7cb4H0` | API |
| Playlist "Shiv Chalisa 43 — पूरी श्रृंखला (Day 1–43)" | ✅ `PLKYGVOH2o0a8`, Day 1 added | public playlist page |
| Home section | ✅ `UCaEn2677hRCSh03kbhy2kqg.jNQXAC9IVRw` | public channel page |
| About links (playlist, site, privacy, terms, mediakit) | ✅ All 5 live | public About page |
| Pinned first comment | ✅ Posted, visible | watch page |
| Custom thumbnail (Day 1) | ✅ Set (200) | `thumbnails.set` response |
| Phone verification | ✅ Done (by user) | unlocks custom thumbnails |

Day 1 Short published publicly: `https://youtube.com/shorts/gJBHA7cb4H0` (31 s, 13 tags, full description, pinned comment).

---

## 9. Test status (current)

- Python light suite: `pytest -m "not heavy"` → **104 passed, 6 deselected**.
- Relay: `npx tsc --noEmit` clean; `npx vitest run` → **28 passed**.
- `python scripts/secret_scan.py` → clean.
- `python scripts/doctor.py` → PASS.
- `python scripts/run_all_checks.py` → runs pytest + vitest + secret_scan + doctor.

---

## 10. Open issues (`docs/FOUND_ISSUES.md`)

1. `content_engine.generate_script` computes a judge scorecard but never persists it through `script_store.save_script` on the batch path.
2. `planner.special_days` covers Shivratri/Kartik Purnima/Mahashivratri only; other festivals not generated.
3. `optimizer` reward/floor/cap not wired into `planner.choose_arm`.
4. `pdfgen` and `monetisation` unreviewed stubs.
5. `analytics`, `lessons_memo`, `knowledge`, `quality_score` partial / not wired.
6. `osx/` generators untested on Windows.
7. `simulate_offline.py` only calls vitest.
8. `audio_mix_graph` sidechain assumes stereo bed; procedural bed is mono.
9. `edge-tts` rarely emits `SentenceBoundary`; cut snapping depends on `sentence_starts_from`, unverified.
10. `gather_shots` downloads at source resolution; large clips inflate work-dir.
11. `validate()` runs ffprobe/ffmpeg filters ~10 s per render.
12. Relay migration `004_queue_resilience.sql` not applied to remote Supabase (blocks `recoverStuck`/`relay_errors`).
13. Relay has no `/chalisa` page (returns 404) though `index.ts` routes it to ASSETS.
14. Custom thumbnails need phone-verified channel status (now done).
15. `/api/factory/approve` is public but queue-guarded; residual risk that anyone with a queued reel_id could approve it.
16. Worker has no YouTube OAuth creds; analytics relies on the laptop snapshot (up to ~1 tick stale). IG analytics empty until H3.
17. `render_reel` hard-fails narration still >58s after 1.08x speed-up; planner doesn't pre-filter by measured TTS duration.

---

## 11. What's next

- **H2**: user reviews the Day 2 reel `4ad5cb0d-…` preview in the dashboard (`/dashboard`) and clicks **Approve**. The daemon syncs the approval back (`pending_approval` → approved `rendered` buffer).
- **H3**: user flips `posting_enabled` and turns Make scenarios ON.
- Apply migration `004_queue_resilience.sql` to remote Supabase.
- Heavy Pass: remaining items in `docs/HEAVY_QUEUE.md`.
- Optional: create `/chalisa` page on the relay (About link currently points at `/`).
- Engagement module (comment polling/replies) gated behind `engagement.enabled` (currently false).

---

## 12. Key files

- `AGENTS.md` — standing rules (truth over progress, stubs labelled, secrets, human gates, compute policy).
- `docs/STATE.md` — module status table (user has uncommitted edits; not touched).
- `docs/FOUND_ISSUES.md` — out-of-scope issues.
- `docs/HEAVY_QUEUE.md` — heavy verification queue + verified results.
- `docs/V5_SUMMARY.md`, `docs/V6_AUDIT.md` — phase history.
- `RUNBOOK.md` — commands.
- `config/config.yaml` — all configuration.
- `scripts/channel_setup.py`, `scripts/channel_branding.py` — YouTube channel page setup (idempotent).
- `scripts/youtube_post_day1.py` — Day-1 publish metadata.
- `src/factory/youtube_upload.py` — upload + first comment.
- `relay/src/*` — Cloudflare Worker.
- `.github/workflows/render.yml` — cloud render cron.