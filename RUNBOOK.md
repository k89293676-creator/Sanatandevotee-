# Runbook

## Prerequisites
- Python 3.11, Node 20+, ffmpeg with libass/harfbuzz on PATH.
- `config/config.yaml` present; secrets via `python scripts/set_secret.py`.
- `ALLOW_HEAVY=1` only for heavy commands.

## Light checks (run before any commit)
```powershell
python -m pytest -m "not heavy" -q
python scripts/secret_scan.py
python scripts/doctor.py
cd relay; npx tsc --noEmit; npx vitest run
```

## Generate scripts (batch)
```powershell
python scripts/generate_all.py
```

## Render
- Single: `python scripts/render_one.py --uuid <uuid>` (heavy)
- Batch: `ALLOW_HEAVY=1 python scripts/render_batch.py --limit 3 --upload` (heavy)

## Sync to relay
```powershell
python scripts/sync_now.py
```

## Text verification (H1 gate — never sets verified_flag)
```powershell
python scripts/verify_text.py --report
```

## Daemon (Windows)
```powershell
pythonw src/factory/daemon.py
```

## Human gates
- H1: verify verse text (`docs/TEXT_REVIEW.md`), then manually set `verified_flag=1`.
- H2: approve a reel (`docs/REVIEW_CHECKLIST.md`), then set `approved_at`.
- H3: flip `posting_enabled` (do not do this in code).

## Heavy Pass
See `docs/HEAVY_QUEUE.md`. All heavy tests are marked `@pytest.mark.heavy`.