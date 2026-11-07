import sys, logging, io
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.factory.logging_setup import setup_logging, SecretFilter

def test_masking():
    f = SecretFilter()
    rec = logging.LogRecord("x", logging.INFO, "", 0, "token=[FAKESECRETVALUE]", (), None)
    assert f.filter(rec)
    assert "REDACTED" in rec.msg or "EAAG" not in rec.msg