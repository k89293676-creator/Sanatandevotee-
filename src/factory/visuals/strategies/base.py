"""Base visual strategy."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List

@dataclass
class Shot:
    i: int
    source: str  # image|video|procedural
    duration: float
    motion: str
    overlay: str

@dataclass
class Timeline:
    shots: List[Shot]
    strategy: str

class Strategy:
    name: str
    def plan(self, spec, n: int) -> Timeline:
        raise NotImplementedError
    def needs(self) -> dict:
        return {"keys": [], "network": False}