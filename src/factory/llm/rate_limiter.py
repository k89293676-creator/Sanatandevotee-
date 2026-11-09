"""Token-bucket rate limiter for Groq."""
from __future__ import annotations
import time
from collections import deque

class RateLimiter:
    def __init__(self, rpm: int = 30, tpm: int = 6000, daily_tokens: int = 100000, soft_stop_pct: float = 0.85):
        self.rpm = rpm
        self.tpm = tpm
        self.daily_tokens = daily_tokens
        self.soft_stop_pct = soft_stop_pct
        self._requests = deque()
        self._tokens_today = 0
        self._day_start = time.time()

    def _reset_day_if_needed(self):
        if time.time() - self._day_start > 86400:
            self._tokens_today = 0
            self._day_start = time.time()

    def can_proceed(self, est_tokens: int = 500) -> bool:
        self._reset_day_if_needed()
        if self._tokens_today + est_tokens > self.daily_tokens * self.soft_stop_pct:
            return False
        now = time.time()
        while self._requests and now - self._requests[0] > 60:
            self._requests.popleft()
        if len(self._requests) >= self.rpm:
            return False
        return True

    def record(self, tokens: int):
        self._requests.append(time.time())
        self._tokens_today += tokens

    def wait_if_needed(self):
        while not self.can_proceed():
            time.sleep(1)