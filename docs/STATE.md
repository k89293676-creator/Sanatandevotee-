# State

## Module Status Table

| Module/Script | Status | Notes |
|---|---|---|
| src/factory/config.py | REAL | load_config, paths |
| src/factory/db.py | REAL | SQLite WAL, 13 tables |
| src/factory/secrets_store.py | REAL | keyring |
| src/factory/logging_setup.py | REAL | redaction (9 patterns) |
| src/factory/notify.py | REAL | Telegram send |
| src/factory/verses.py | REAL | load/upsert/get |
| src/factory/scriptgen.py | REAL | Groq primary, pydantic, safety filter |
| src/factory/content_engine.py | PARTIAL | multi-pass + judge exist; judge hard-coded 80/60, not stored in script_scores; not wired to generation |
| src/factory/planner.py | PARTIAL | slot logic works; special days placeholder; optimizer not wired |
| src/factory/optimizer.py | PARTIAL | ensure_arms, weights; no reward/floor/cap wired to planner |
| src/factory/tts.py | REAL | edge-tts/gTTS/Piper, Speech, synthesize_chunks |
| src/factory/captions.py | REAL | chunking, 3 timing methods, build_ass |
| src/factory/render.py | REAL | RenderSpec, manifest, validate, contact_sheet; quality_score base 100 (hard-coded) |
| src/factory/fonts.py | REAL | fontTools coverage check |
| src/factory/visuals/ | PARTIAL | chain + providers real; strategies/ STUB classes |
| src/factory/audio_bed.py | REAL | procedural bed, -28dB, fade |
| src/factory/sync.py | REAL | HMAC, upload, verify, enqueue |
| src/factory/power.py | REAL | battery/AC, can_render, max_threads |
| src/factory/daemon.py | PARTIAL | lock + tick; tick logs only, no real render/upload/enqueue |
| src/factory/pdfgen.py | STUB | not reviewed |
| src/factory/monetisation.py | STUB | not reviewed |
| src/factory/analytics.py | PARTIAL | import_insights_csv, youtube_stats, weekly_report |
| src/factory/lessons_memo.py | PARTIAL | module exists, not wired to daemon |
| src/factory/knowledge.py | PARTIAL | fetch_card exists, not run |
| src/factory/quality_score.py | PARTIAL | function exists, not wired to render manifest |
| src/factory/osx/ | PARTIAL | generators exist, not installed/tested |
| scripts/validate_inputs.py | REAL | live checks |
| scripts/generate_all.py | REAL | verses→scripts→plan |
| scripts/render_batch.py | STUB | lists planned only |
| scripts/sync_now.py | REAL | relay URL from config |
| scripts/smoke_test.py | REAL | config + DB |
| scripts/simulate_offline.py | STUB | calls vitest only |
| scripts/install.py | PARTIAL | deps + DB + hooks + autostart (Windows) |
| scripts/uninstall.py | REAL | removes task |
| scripts/doctor.py | REAL | all checks (fixed or True) |
| scripts/secret_scan.py | REAL | working tree + gitleaks |
| scripts/set_secret.py | REAL | clipboard + paste + validation + live checks |
| scripts/copy_secret.py | REAL | generate/copy |
| scripts/clip_secret.py | REAL | clipboard copy + clear |
| scripts/render_one.py | REAL | full render pipeline |
| scripts/gen_unit1.py | REAL | generate unit 1 meaning |
| scripts/bench_llm.py | REAL | benchmark Groq models |
| scripts/special_days.py | PARTIAL | ephem, approximations |
| scripts/verify_text.py | STUB | prints instructions only |
| scripts/youtube_auth.py | PARTIAL | real OAuth flow, not tested |
| scripts/check_sync.py | STUB | prints estimates |
| scripts/run_all_checks.py | REAL | pytest + vitest + secret_scan + doctor |
| relay/ (all) | REAL | deployed, selfcheck green |

## Done (v6)
- U0: tag pre-v6, backup, V6_AUDIT.md
- U1: Groq client, bench, rate_limiter, templates, llm_usage/llm_cache tables, content_engine (9 formats, multi-pass, judge), LLM_BENCH.md
- U2: knowledge module (fetch_card, generate_cards)
- U3: content engine with 9 formats, multi-pass, judge scorecard, hook archetypes, rule checks
- U4: 7 visual strategies (stub classes with plan/needs)
- U5: captions (chunking, 3 timing), audio (sidechain, loudnorm), sync validator (stub)
- U6: daemon tick (content_job, plan, render, optimizer), quality score
- U7: planner (slot A/B), optimizer (reward, floor), analytics (import, youtube_stats, weekly_report), lessons_memo
- U8: metadata/SEO, YouTube upload module, site pages, pdfgen (unreviewed)
- CO-1: verify_text.py (stub)
- CO-2: simulate_offline (calls vitest)
- CO-3: render_batch (lists planned)
- CO-4: youtube_auth (real OAuth)
- CO-5: special_days (ephem, approximations)
- CO-6: optimizer (reward, floor, cap)
- CO-7: pdfgen/monetisation (not reviewed)
- CO-8: run_all_checks (real output)
- CO-9: relay vitest (2 tests)
- CO-10: install.py (registers autostart)

## Tests
- pytest 21/21, vitest 2/2, secret_scan clean, doctor PASS

## Day 1 Reel
- MP4: media/renders/d3425fcc-54ff-4a99-872c-525acd34c883.mp4
- 38.5s, 1080x1920, 8 shots, -14.0 LUFS, ok=True
- Contact sheet: media/work/d3425fcc-54ff-4a99-872c-525acd34c883_sheet.jpg

## Human Gates
- H1: verse text review (verified_flag=0)
- H2: Day 1 reel approval (awaiting "approved")
- H3: Make scenarios ON (scenarios OFF)

## Session update — Phases A–D (2026-11-09)

Corrected module statuses (supersedes stale rows above where they conflict):
- src/factory/render.py | REAL | measured score_render (QUALITY_WEIGHTS), sentence-snapped cuts (plan_cut_times), varied transitions (plan_transitions), sidechain audio_mix_graph, phash dedupe, strategy-driven gather_shots.
- src/factory/phash.py | REAL | dHash + is_duplicate, _hash_or_none.
- src/factory/tts.py | REAL | synthesize_chunks preserves boundary kind.
- src/factory/jobs.py | REAL | build_spec/render_reel_row/mark_failed/upload_reel; daemon renders+uploads.
- src/factory/daemon.py | REAL | tick renders and uploads; still gated by power.can_render.
- src/factory/visuals/strategies/ | REAL | 8 strategies incl. mixed_montage default; get_strategy fallback mixed_montage.
- scripts/render_batch.py | REAL | real loop via jobs, --limit/--upload, ALLOW_HEAVY guard.
- scripts/special_days.py | REAL (approx) | tithi via ephem elongation; Kartik Purnima, Shivratri (sidereal Kumbha); _note per year.
- scripts/verify_text.py | REAL | normalize/locate/boundary compare; exit 0/1/2; never touches verified_flag.
- scripts/check_sync.py | REAL | parse_ass/speech_onsets/pair_offsets.
- relay make_api.ts | REAL | claim_due_reel, claimed→handed_off, credit gate, rate limit, idempotent ack.
- relay make_health.ts | REAL | unacked→unknown + dead-man alerts; wired in scheduled.ts.
- relay youtube | REAL (gated) | YOUTUBE_ENABLED + refresh token, yt_status filter, conditional PATCH, 5/day meter.

Tests (light, current):
- Python: `pytest -m "not heavy"` → 97 passed, 6 deselected.
- Relay: `npx vitest run` → 28 passed; `npx tsc --noEmit` clean.
- secret_scan: clean; doctor: PASS.

Heavy: see docs/HEAVY_QUEUE.md. Verified 2026-11-09: test_render.py 3 passed (full render+validate, manifest shaping, validate-fails). Other heavy items remain pending.

Human gates unchanged: H1 verse text, H2 reel approval, H3 Make ON — not touched by this session.