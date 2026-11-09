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