"""Common provider interface."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol


@dataclass
class Asset:
    provider: str
    asset_id: str
    url: str
    source_page: str
    uploader: str
    license: str
    kind: str  # image|video


class Provider(Protocol):
    name: str
    def available(self) -> bool: ...
    def search(self, keywords: list[str], orientation: str, kind: str) -> List[Asset]: ...
    def download(self, asset: Asset, dest: Path) -> bool: ...