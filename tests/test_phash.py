"""Light tests: dHash dedupe rejects the same photo served under a new asset id."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw                              # noqa: E402

from src.factory.phash import THRESHOLD, dhash, distance, is_duplicate   # noqa: E402
from src.factory.render import _hash_or_none                  # noqa: E402


def _pattern(path: Path, shift: int = 0) -> Path:
    im = Image.new("RGB", (180, 320), "black")
    d = ImageDraw.Draw(im)
    for x in range(0, 180, 20):
        d.rectangle([x + shift, 0, x + shift + 10, 320], fill="white")
    im.save(path)
    return path


def test_identical_images_hash_equal(tmp_path):
    a = _pattern(tmp_path / "a.png")
    b = _pattern(tmp_path / "b.png")
    ha, hb = dhash(a), dhash(b)
    assert distance(ha, hb) == 0
    assert is_duplicate(ha, [hb])


def test_near_identical_crop_is_duplicate(tmp_path):
    a = _pattern(tmp_path / "a.png")
    b = _pattern(tmp_path / "b.png", shift=2)          # barely shifted stripes
    assert is_duplicate(dhash(a), [dhash(b)])


def test_different_images_are_not_duplicates(tmp_path):
    a = _pattern(tmp_path / "a.png")
    b = Image.new("RGB", (180, 320), "white")
    ImageDraw.Draw(b).rectangle([10, 10, 170, 310], fill="black")
    b.save(tmp_path / "b.png")
    d = distance(dhash(a), dhash(b))
    assert d > THRESHOLD
    assert not is_duplicate(dhash(a), [dhash(b)])


def test_unreadable_download_hashes_to_none(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"\x00")
    assert _hash_or_none(bad) is None
    assert _hash_or_none(tmp_path / "missing.jpg") is None
