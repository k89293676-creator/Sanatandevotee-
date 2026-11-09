# Found Issues (out of scope for this session; do not auto-fix)

- `content_engine.generate_script` computes a judge scorecard but never persists it through `script_store.save_script` for the batch path (`scripts/generate_all.py`); only the daemon path saves.
- `planner.special_days` now computes real tithi for Shivratri/Kartik Purnima and Mahashivratri, but other festivals (Navratri, Diwali, etc.) are not yet generated; `_note` labels approximations.
- `optimizer` reward/floor/cap logic exists but is not wired into `planner.choose_arm` beyond `choose_arm`; reward updates are only called from the daemon path.
- `pdfgen` and `monetisation` modules are unreviewed stubs.
- `youtube_auth` / `youtube_upload` gating is implemented but never exercised end-to-end (no real OAuth run in this session).
- `analytics.import_insights_csv`, `youtube_stats`, `weekly_report` are partial.
- `lessons_memo` exists but is not wired into the daemon.
- `osx/` generators target macOS; untested on Windows.
- `simulate_offline.py` only calls vitest, not the Python pipeline.
- `audio_mix_graph` sidechain assumes the bed is stereo after `aresample`; the procedural bed is mono and gets upmixed. Verify in Heavy Pass.
- `edge-tts` rarely emits `SentenceBoundary`; cut snapping depends on `sentence_starts_from`, which is unverified against real boundary text.
- `gather_shots` video clips are downloaded at source resolution and only resized in ffmpeg; large clips can inflate work-dir size.
- `validate()` runs ffprobe/ffmpeg filters that take ~10s; scoring calls it once per render.