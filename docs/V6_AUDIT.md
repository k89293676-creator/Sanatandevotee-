# V6 Audit
## Real (verified)
- Factory: config, db (SQLite WAL), secrets (keyring), logging+redaction, verses (42 units, verified_flag=0), scriptgen (Groq gpt-oss-20b, pydantic, safety filter), planner (INSERT fixed), optimizer (ensure_arms), TTS (edge-tts + gTTS + Piper), captions (chunking, edge/whisper/proportional), render (RenderSpec, manifest, Ken Burns crop-pan, parallel shots, xfade, libass shaping=complex, two-pass loudnorm, validate, contact_sheet), fonts (coverage check), visuals (Pixabay/Wikimedia/Pollinations/procedural), audio_bed (-28dB, fade), sync (HMAC, upload-url, verify URL), power, daemon (msvcrt lock, real tick), osx (Windows task XML), pdfgen, monetisation, notify, youtube_upload.
- Relay: Cloudflare Worker deployed, /api/factory/*, /api/make/*, /selfcheck, cron, KV, Supabase migrations.
- Tests: pytest 20 pass, vitest 1 pass, secret_scan clean, doctor PASS.
- Day 1 reel rendered & validated (38.5s, 8 shots, -14.0 LUFS, ok=True).

## Stubs (not yet real)
- simulate_offline.py: prints PASS without simulating.
- render_batch.py: placeholder.
- youtube_auth.py: stub.
- install.py: does not register autostart.
- daemon.tick(): renders but does not upload/enqueue (no real upload loop).
- sync.py: request_upload_url returns Supabase signed URL (untested with real upload).
- Special days: placeholders (every Monday, fixed dates).
- Optimizer: no reward calculation, no exploration floor, no 60% cap.
- pdfgen.py, monetisation.py: not reviewed.
- relay/: not fully audited for upload-url, selfcheck, buffer alerts, daily/weekly jobs, asset cleanup.

## Verified Live
- Worker /status.json 200, /api/make/ping 200, /api/factory/selfcheck all green.
- Telegram "relay OK" sent.
- Supabase migrations applied.
- Make Slot A/B returned empty:true on test (auth works).

## Not Done (carry-over CO-1 to CO-10)
- Verse text two-source diff (verified_flag=0).
- simulate_offline real.
- render_batch real.
- youtube_auth real OAuth.
- Special days with ephem.
- Optimizer reward/floor/cap.
- pdfgen/monetisation/relay audit.
- run_all_checks real output.
- Relay /api/make/*, selfcheck, buffer alerts verified with vitest.
- Autostart proven after log-off/on.