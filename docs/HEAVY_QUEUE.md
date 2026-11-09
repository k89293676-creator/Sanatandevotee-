# Heavy Verification Queue (Phase D + media)

These items require `ALLOW_HEAVY=1` and real compute. Do **not** run during the normal development loop; verify in the Heavy Pass only.

| # | Item | Command / Test | Why heavy |
|---|------|----------------|-----------|
| 1 | End-to-end reel render | `ALLOW_HEAVY=1 python -m pytest tests/test_render.py -q` | ffmpeg encode, TTS-adjacent audio, ~60s |
| 2 | `test_full_render_and_validate` (full render + validate) | same as #1 | ffmpeg, loudness scan |
| 3 | `test_manifest_uses_complex_shaping_and_distinct_shots` | same as #1 | ffmpeg |
| 4 | Sentence-snapped cut timing against real TTS | render a real reel (edge-tts) and inspect `cut_times`, `cut_source` | TTS network + render |
| 5 | Sidechain ducking audibility + loudness | render + listen / measure LUFS in gaps | audio render |
| 6 | Transition variety visual check | `contact_sheet` on a real render | render |
| 7 | Perceptual dedupe against live Pixabay | render with network providers enabled | network + render |
| 8 | `render_batch.py` loop | `ALLOW_HEAVY=1 python scripts/render_batch.py --limit 2` | renders N reels |
| 9 | `simulate_offline.py` | `ALLOW_HEAVY=1 python scripts/simulate_offline.py` | full pipeline |
| 10 | `test_render.py` manifest field assertions (`cut_times`, `shot_lengths_s`, `transitions`, `cut_source`) | #1 | depends on render |
| 11 | Real Whisper/ASR caption check (if ever enabled) | heavy | GPU/CPU |

Mark any new slow test with `@pytest.mark.heavy` in `pytest.ini`-registered marker.

## Verified in Heavy Pass (2026-11-09)

- `tests/test_render.py::test_full_render_and_validate` — PASSED (318.59s). Full render + validate, `v["ok"]` True; manifest cut/length/transition assertions passed.
- `tests/test_render.py::test_manifest_uses_complex_shaping_and_distinct_shots` — PASSED.
- `tests/test_render.py::test_validate_fails_for_the_right_reason` — PASSED.
- Real reel via `jobs.render_reel_row` (meaning format, 36.4s) — PASSED (340.4s). 8/8 distinct assets, `cut_source=mixed`, transitions varied, `quality_score=100`, validate `ok=True`, LUFS -14.0, 0 silences, 12 scene changes.
- `contact_sheet` generated for the real reel (`media/contact_heavy.jpg`).
- `scripts/render_batch.py --limit 1` — success path PASSED (rendered 1, failed 0, 528.1s); failure path (narration too long) handled gracefully and marked failed.
- `scripts/simulate_offline.py` — PASSED (28 relay tests, exit 0).
- Total heavy suite for `test_render.py`: 3 passed.