"""Logging with secret redaction and rotation."""
from __future__ import annotations
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"),
    re.compile(r"EAAG\w+"),          # Meta tokens
    re.compile(r"\d{8,}:[A-Za-z0-9_-]{30,}"),  # Telegram bot token
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),      # Google
    re.compile(r"sbp_[A-Za-z0-9]{30,}"),       # Supabase
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT
]


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pat in SECRET_PATTERNS:
            msg = pat.sub("[REDACTED]", msg)
        record.msg = msg
        record.args = ()
        return True


def setup_logging(name: str = "factory", level: int = logging.INFO) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        fh = RotatingFileHandler(LOG_DIR / f"{name}.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        fh.addFilter(SecretFilter())
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.addFilter(SecretFilter())
        sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(sh)
    return logger


def mask_value(v: str | None) -> str:
    if not v:
        return "<missing>"
    return "..." + v[-4:] if len(v) > 4 else "****"