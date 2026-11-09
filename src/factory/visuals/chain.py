"""Visual provider chain: pixabay -> wikimedia_commons -> pollinations (procedural is the caller's last resort)."""
from __future__ import annotations
from pathlib import Path
import shutil
from .providers.base import Asset, NEGATIVE_TAGS
from .providers.pixabay import PixabayProvider
from .providers.wikimedia import WikimediaProvider
from .providers.pollinations import PollinationsProvider
from ..config import load_config, project_root

from ..logging_setup import setup_logging

log = setup_logging("visuals")
PROVIDERS = {"pixabay": PixabayProvider, "wikimedia_commons": WikimediaProvider, "pollinations": PollinationsProvider}

MANDATORY_TAGS = ["himalayan peak", "lord shiva trident", "kailash mountain",
                  "holy river ganges", "ancient indian temple stone",
                  "spiritual meditation glow"]
CONTEXT_CLUSTERS = {
    "shiva": ["lord shiva trident", "mahadev", "rudraksha", "nandi"],
    "temple": ["ancient indian temple stone", "hindu temple", "diya light", "sacred flame"],
    "himalaya": ["himalayan peak", "kailash mountain", "mountain mist"],
    "meditation": ["spiritual meditation glow", "yoga", "incense smoke"],
    "ganges": ["holy river ganges", "sacred river"],
}


def contextualize(keywords: list[str]) -> list[str]:
    out: list[str] = []
    for k in (keywords or []):
        kl = k.lower()
        out.append(k)
        for key, vals in CONTEXT_CLUSTERS.items():
            if key in kl:
                out.extend(vals)
    # enforce at least two mandatory cultural tags
    for t in MANDATORY_TAGS[:2]:
        if t not in out:
            out.append(t)
    # de-dupe while preserving order
    seen, uniq = set(), []
    for k in out:
        if k.lower() not in seen:
            seen.add(k.lower())
            uniq.append(k)
    return uniq[:10]


def _relevant(asset: Asset) -> bool:
    text = f"{asset.tags} {asset.source_page} {asset.url}".lower()
    return not any(neg in text for neg in NEGATIVE_TAGS)


def _local_pool() -> list[Path]:
    d = project_root() / "assets" / "stock" / "devotional"
    d.mkdir(parents=True, exist_ok=True)
    return [p for p in d.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".mp4")]


def get_chain() -> list:
    names = load_config().get("visuals", {}).get("providers", list(PROVIDERS))
    return [PROVIDERS[n]() for n in names if n in PROVIDERS]


def fetch_asset(keywords: list[str], orientation: str, kind: str, dest: Path, seed: int = 0,
                exclude_ids: set | None = None) -> Asset | None:
    excluded = exclude_ids or set()
    ctx = contextualize(keywords)
    # Try providers
    collected: list[Asset] = []
    for prov in get_chain():
        try:
            if not prov.available():
                continue
            assets = prov.search(ctx, orientation, kind) if prov.name != "pollinations" \
                else prov.search(ctx, orientation, kind, seed=seed)
        except Exception as e:
            log.warning("%s search failed: %s", prov.name, e)
            continue
        for a in assets[:10]:
            if a.asset_id in excluded:
                continue
            if not _relevant(a):
                continue
            collected.append(a)
            if len(collected) >= 3:
                break
        if len(collected) >= 3:
            break
    for a in collected:
        try:
            if a.provider == "pollinations":
                # pollinations download handled by provider
                pass
            if _download(a, dest):
                return a
        except Exception as e:
            log.warning("%s download failed: %s", a.provider, e)
    # local pool fallback
    for p in _local_pool():
        if p.name in excluded:
            continue
        try:
            shutil.copy2(p, dest)
            if dest.exists() and dest.stat().st_size > 0:
                return Asset(provider="local_pool", asset_id=p.name, url=str(p),
                            source_page="", uploader="local", license="local", kind=kind, tags="devotional")
        except Exception as e:
            log.warning("local pool copy failed: %s", e)
    return None


def _download(asset: Asset, dest: Path) -> bool:
    # delegate to provider download by re-instantiating? Simpler: httpx stream
    import httpx
    if asset.provider == "local_pool":
        return dest.exists()
    if asset.url.startswith("http"):
        try:
            with httpx.stream("GET", asset.url, timeout=120, follow_redirects=True) as r:
                if r.status_code != 200:
                    return False
                with dest.open("wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            return dest.exists() and dest.stat().st_size > 0
        except Exception:
            return False
    return False