# V5 Upgrade Summary: Shiv Chalisa Reel Pipeline

## 0. How We Worked
- Vertical slices: one verse end-to-end before batch.
- Long jobs run in background with polling; hard timeout 10 min/ffmpeg, 15 min/reel.
- Honesty: no fake PASS; every acceptance test run with real output in docs/VERIFICATION.md.
- Secrets never printed; stored via scripts/set_secret.py --from-clipboard / --paste into keychain or wrangler.
- posting_enabled=false; Make scenarios OFF until user approves (H3).

## 1. Phase 0: Freeze & Audit
- Tagged `pre-v5`; backed up `data/factory.db` to `backups/pre-v5/`.
- DB cleanup: deleted 48 duplicate planned reels (no video_path); marked 1 handmade script as `handmade_test`.
- Deleted throwaway scripts: render_day1.py, fix_render_day1.py, dl_shots.py; removed `src/factory/visuals.py` (package shadows module).
- Created `docs/STATE.md`, `docs/V5_AUDIT.md`, `docs/ROLLBACK_V4.md`.

## 2. Phase 1: Scripts Become Real
- `doctor.py`: real checks (ffmpeg, libass, harfbuzz, fonts, disk, DB, secret_scan, keychain names, Worker status).
- `simulate_offline.py`: stub (to be wired to vitest with fake clock).
- `render_batch.py`: placeholder (to implement).
- `smoke_test.py`: loads config + DB.
- `install.py`: venv + deps + DB init + git hooks.
- `secret_scan.py`: scans working tree + gitleaks; patterns for Telegram, Google, JWT, sb_secret_, Pixabay, Make key (mk_ prefix).
- `validate_inputs.py`: removed Pexels; added Pixabay, Gemini, Telegram, Supabase (via Worker), Make ping, Worker auth.
- `set_secret.py`: --from-clipboard, --paste, --target, validation before clearing clipboard, live checks (PASS/FAIL only).
- `copy_secret.py`: generate/copy to keychain + wrangler.
- `clip_secret.py`: copy keychain secret to clipboard, clear after 60s.
- `sync_now.py`: relay URL from config.yaml.
- `youtube_auth.py`: stub (to implement real OAuth).
- `run_all_checks.py`: runs pytest, vitest, secret_scan, doctor.
- Config delta applied: relay.url, llm.model, visuals (min_shots 8, shot_seconds), render (profile, crossfade, caption, loudness, budget), hook_styles, formats, visual_styles, voices, youtube.

## 3. Phase 2: Verse Text
- 42 units in `data/packs/shiv_chalisa/verses.json` (opening doha, 40 chaupai, closing doha). N derived = 42.
- verified_flag=0 (pending two-source diff). docs/TEXT_REVIEW.md generated with all 42 units for user verification.
- Kinds: doha, chaupai, closing (to be migrated to doha_open/chaupai/doha_close).

## 4. Phase 3: Script Generation
- Gemini free tier unavailable (billing required). Groq (openai/gpt-oss-20b) used as primary.
- scriptgen.py: pydantic validation, safety filter, resumable, 4 formats (meaning, story, when, recital).
- Unit 1 meaning script generated: 87 words, 37.49s TTS, safety passed, 5 hooks with all 5 style tags.
- Viral hook framing integrated (crisis_solver, curiosity, deep_meaning).
- visual_keywords filtered for banned generic terms.

## 5. Phase 4: Render Pipeline Rebuild (Patch 1)
- `src/factory/render.py`: RenderSpec dataclass, manifest.json per reel, real audio length (no -shortest), 8-12 shots, crop-pan Ken Burns (no zoompan), parallel shots (ThreadPoolExecutor), xfade 0.4s, libass with shaping=complex, two-pass loudnorm, validate() with blackdetect/silencedetect/scene-change/flat-colour, contact_sheet().
- `src/factory/captions.py`: phrase chunking at danda, timing order edge-tts boundaries → faster-whisper → proportional on real audio length, difflib alignment, ASS styles (Hook, Badge, Captions, Roman, CTA).
- `src/factory/tts.py`: returns Speech(path, duration, engine, boundaries); one edge-tts pass gives audio + boundaries; cached with sidecar JSON; Piper looks only in assets/voices.
- `src/factory/fonts.py`: fontTools glyph-coverage check; render refuses if any on-screen string has a missing glyph.
- `src/factory/visuals/procedural.py`: always-available offline stills, different per style/seed.
- `src/factory/visuals/chain.py`, providers: per-shot seeds, failures logged and skipped, lazy httpx import.
- `assets/fonts/DejaVuSans-Bold.ttf`: Latin font for Roman line.
- `scripts/render_one.py`: laptop check with real TTS + providers, prints every measurement.
- Tests: 5 tests (tofu bug, timing methods, full render + validate, bad clip fails for right reasons).
- Bug fixes: Devanagari shaping (shaping=complex), badge/CTA Devanagari+digits only.

## 6. Phase 5: Planner, Special Days, Optimizer
- planner.py: INSERT bug fixed (13 placeholders), uses make slots, jitter 0, cap 2/day.
- Special days: placeholders (to be replaced with ephem + panchang cross-check).
- optimizer.py: ensure_arms reads from config; reward calculation to be implemented.

## 7. Phase 6: Daemon, Sync, Autostart, Relay
- daemon.py: lock uses msvcrt (not os.kill), relay URL from config, tick() does real work (heartbeat, state, render, plan, optimizer).
- sync.py: request_upload_url, Content-Length, verify_public_url, idempotent enqueue payload.
- osx/windows.py: fixed module path (src.factory.daemon), removed Duration=P1D, venv python.
- power.py: Linux branch fixed.
- Relay audit: /api/factory/upload-url, /enqueue, /state, /heartbeat, /weights, /selfcheck; /api/make/* per v4 spec.
- /api/factory/selfcheck: booleans only (supabase_ok, telegram_ok, kv_ok, make_key_set, length bucket).

## 8. Phase 7-8: Secrets, YouTube, Site
- Secrets: /api/factory/selfcheck all green (supabase, kv, telegram, make_key).
- TELEGRAM_CHAT_ID derived (1374009217), stored in keychain + Worker, "relay OK" sent.
- YouTube: youtube_upload.py module (resumable, laptop-side, scheduled upload). youtube_auth.py stub.
- Site/PDF: pdfgen.py, monetisation.py (not fully reviewed).

## 9. Phase 9: E2E Slice
- Day 1 reel rendered and validated: 38.5s, 8 shots, -13.9 LUFS, edge_boundary timing, ok=True.
- Contact sheet generated.
- Human gate H2: awaiting user "approved".

## Infrastructure
- Cloudflare Worker: https://chalisa-relay.mew92724.workers.dev (KV TOKENS, cron * * * * and 30 18 * * *, observability OFF).
- Supabase: migrations 001+002 applied (relay_queue, relay_comments, relay_insights, relay_account, relay_state, relay_events, claim_due_reel).
- Make.com: Slot A (06:30 IST) and Slot B (19:00 IST) scenarios built, OFF, returned empty:true on test.
- posting_enabled=false in Supabase relay_state.
- TELEGRAM_BOT_TOKEN, SUPABASE_SERVICE_KEY, MAKE_KEY, FACTORY_API_KEY, FACTORY_HMAC_SECRET, TELEGRAM_CHAT_ID stored as Worker secrets.

## Remaining Work
- H1: verse text review against printed copy (verified_flag=0).
- H2: Day 1 reel approval.
- H3: turn Make scenarios ON after first post.
- Phase 2-9: full verse verification, script generation for all 42 units, planner/special days/optimizer, daemon/autostart, YouTube scheduled upload, site/PDF.
- run_all_checks.py real output pasted into docs/VERIFICATION.md.