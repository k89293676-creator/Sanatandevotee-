"""Build data/special_days.json for planning (Pradosh, Shivratri, Kartik Purnima, Shravan Mondays).

Status: **computed approximation**. Tithi and full-moon dates come from ephem
(ecliptic moon-sun elongation at 18:00 IST, New Delhi). Shravan Mondays are
*not* lunar-month accurate: they are the Mondays of July-August, and every
generated year carries a `_note` saying so. A human should check these dates
against the panchang they follow (regional calendars disagree by a day).

`ephem` is optional: without it the script still writes a file, using clearly
labelled fallback dates, so planning never crashes on a missing dependency.

Usage:
    python scripts/special_days.py [--start-year 2026] [--years 5] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "special_days.json"

try:  # optional dependency
    import ephem  # type: ignore
    HAS_EPHEM = True
except Exception:  # pragma: no cover - depends on environment
    ephem = None  # type: ignore
    HAS_EPHEM = False

IST = timezone(timedelta(hours=5, minutes=30))
LAT, LON = "28.6139", "77.2090"   # New Delhi

EPHEM_NOTE = (
    "Computed with ephem at 18:00 IST, New Delhi: tithi from moon-sun ecliptic "
    "elongation; Kartik Purnima from the Kartik new moon; Shivratri filtered by "
    "sidereal sun in Kumbha. Lahiri ayanamsa is approximated, Shravan Mondays are "
    "the Mondays of July-August, and regional panchangs may differ by a day. "
    "Check before relying on a date."
)
FALLBACK_NOTE = (
    "ephem is not installed, so these are fixed approximations only. Install "
    "ephem and re-run scripts/special_days.py for computed dates."
)


def _ayanamsa(year: int) -> float:
    """Approximate Lahiri ayanamsa in degrees (good to ~0.01 deg near 2026)."""
    return 23.85 + (year - 2000) * 0.0139722


def _evening_ist_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 18, 0, tzinfo=IST).astimezone(timezone.utc)


def _observer(when_utc: datetime):
    obs = ephem.Observer()  # type: ignore[union-attr]
    obs.lat, obs.lon = LAT, LON
    obs.date = when_utc
    return obs


def elongation_deg(when_utc: datetime) -> float:
    """Moon minus sun ecliptic longitude in degrees, 0..360 (0 = new moon)."""
    obs = _observer(when_utc)
    sun = ephem.Sun(obs)  # type: ignore[union-attr]
    moon = ephem.Moon(obs)  # type: ignore[union-attr]
    slon = float(ephem.Ecliptic(sun).lon)  # type: ignore[union-attr]
    mlon = float(ephem.Ecliptic(moon).lon)  # type: ignore[union-attr]
    return math.degrees(mlon - slon) % 360.0


def tithi_for_date(d: date) -> int:
    """Lunar day 1..30 (1-15 waxing, 16-30 waning) at 18:00 IST."""
    return int(elongation_deg(_evening_ist_utc(d)) // 12.0) + 1


def sidereal_sun_deg(d: date) -> float:
    """Sun's sidereal (nirayana) ecliptic longitude at 18:00 IST, 0..360."""
    obs = _observer(_evening_ist_utc(d))
    tropical = math.degrees(float(ephem.Ecliptic(ephem.Sun(obs)).lon))  # type: ignore[union-attr]
    return (tropical - _ayanamsa(d.year)) % 360.0


def new_moon_dates(year: int) -> list[date]:
    """Approximate new-moon dates; a tithi can be skipped by daily sampling."""
    out: list[date] = []
    prev = 30
    d = date(year, 1, 1)
    while d.year == year:
        t = tithi_for_date(d)
        if t <= 2 and prev >= 29:          # elongation wrapped past 0
            out.append(d)
        prev = t
        d += timedelta(days=1)
    return out


def _scan(year: int, months: tuple[int, ...], tithis: set[int]) -> list[date]:
    """Dates in `months` whose evening tithi is in `tithis`, collapsing consecutive runs."""
    found: list[date] = []
    d = date(year, months[0], 1)
    end = date(year, months[-1] + 1, 1) if months[-1] < 12 else date(year + 1, 1, 1)
    while d < end:
        if d.month in months and tithi_for_date(d) in tithis:
            # the same tithi can touch two evenings; keep the first of a run
            if not found or (d - found[-1]).days > 1:
                found.append(d)
        d += timedelta(days=1)
    return found


def shravan_mondays(year: int) -> list[str]:
    """Approximation: Mondays in July-August (see module note)."""
    out, d = [], date(year, 7, 1)
    while d.month <= 8:
        if d.weekday() == 0:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def pradosh_vrat(year: int) -> list[str]:
    # Trayodashi (13th tithi) of either fortnight, observed at evening.
    return [d.isoformat() for d in _scan(year, tuple(range(1, 13)), {13, 28})]


def maha_shivratri(year: int) -> list[str]:
    # Krishna Chaturdashi (waning 14th = tithi 29) while the sun is in sidereal
    # Kumbha (Aquarius, 300-330 deg). This skips the Capricorn chaturdashi that
    # also falls in Feb in some years.
    return [
        d.isoformat()
        for d in _scan(year, (2, 3), {29})
        if 300.0 <= sidereal_sun_deg(d) < 330.0
    ][:1]


def kartik_purnima(year: int) -> list[str]:
    # Kartik (Amanta) is the lunar month starting at the new moon whose sidereal
    # sun is in Tula (Libra, 180-210 deg); its purnima is the full moon that closes it.
    kp = next((n for n in new_moon_dates(year) if 180.0 <= sidereal_sun_deg(n) < 210.0), None)
    if kp is None:
        return []
    for off in range(1, 21):
        d = kp + timedelta(days=off)
        if tithi_for_date(d) == 15:
            return [d.isoformat()]
    return []


def _fallback_year(year: int) -> dict:
    return {
        "_note": FALLBACK_NOTE,
        "shravan_mondays": shravan_mondays(year),
        "kartik_purnima": [f"{year}-11-15"],
        "pradosh_vrat": [f"{year}-{m:02d}-{d:02d}" for m in range(1, 13) for d in (13, 28)],
        "maha_shivratri": [f"{year}-02-26"],
    }


def build_days(start_year: int, years: int) -> dict:
    out = {}
    for y in range(start_year, start_year + years):
        if HAS_EPHEM:
            out[str(y)] = {
                "_note": EPHEM_NOTE,
                "shravan_mondays": shravan_mondays(y),
                "kartik_purnima": kartik_purnima(y),
                "pradosh_vrat": pradosh_vrat(y),
                "maha_shivratri": maha_shivratri(y),
            }
        else:
            out[str(y)] = _fallback_year(y)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start-year", type=int, default=date.today().year)
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    days = build_days(args.start_year, args.years)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(days, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", out)
    print("ephem:", HAS_EPHEM, "years:", list(days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
