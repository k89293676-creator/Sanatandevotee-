"""Visual strategies."""
from __future__ import annotations
from .base import Strategy, Timeline, Shot

class AiIllustrated(Strategy):
    name = "ai_illustrated"
    def plan(self, spec, n):
        shots = [Shot(i=i, source="image", duration=4.0, motion="pan", overlay="caption") for i in range(n)]
        return Timeline(shots=shots, strategy=self.name)
    def needs(self): return {"keys": [], "network": True}

class StockMontage(Strategy):
    name = "stock_montage"
    def plan(self, spec, n):
        shots = [Shot(i=i, source="video", duration=3.5, motion="cut", overlay="caption") for i in range(n)]
        return Timeline(shots=shots, strategy=self.name)
    def needs(self): return {"keys": ["pixabay"], "network": True}

class KineticTypography(Strategy):
    name = "kinetic_typography"
    def plan(self, spec, n):
        shots = [Shot(i=i, source="procedural", duration=4.0, motion="pan", overlay="verse_large") for i in range(n)]
        return Timeline(shots=shots, strategy=self.name)
    def needs(self): return {"keys": [], "network": False}

class DiyaLoop(Strategy):
    name = "diya_loop"
    def plan(self, spec, n):
        shots = [Shot(i=i, source="procedural", duration=5.0, motion="parallax", overlay="caption") for i in range(n)]
        return Timeline(shots=shots, strategy=self.name)
    def needs(self): return {"keys": [], "network": False}

class CosmicSky(Strategy):
    name = "cosmic_sky"
    def plan(self, spec, n):
        shots = [Shot(i=i, source="procedural", duration=4.0, motion="parallax", overlay="caption") for i in range(n)]
        return Timeline(shots=shots, strategy=self.name)
    def needs(self): return {"keys": [], "network": False}

class StoryPanels(Strategy):
    name = "story_panels"
    def plan(self, spec, n):
        shots = [Shot(i=i, source="image", duration=4.0, motion="pan", overlay="panel_caption") for i in range(n)]
        return Timeline(shots=shots, strategy=self.name)
    def needs(self): return {"keys": [], "network": True}

class SplitMeaning(Strategy):
    name = "split_meaning"
    def plan(self, spec, n):
        shots = [Shot(i=i, source="procedural", duration=4.0, motion="static", overlay="split") for i in range(n)]
        return Timeline(shots=shots, strategy=self.name)
    def needs(self): return {"keys": [], "network": False}

STRATEGIES = {
    "ai_illustrated": AiIllustrated,
    "stock_montage": StockMontage,
    "kinetic_typography": KineticTypography,
    "diya_loop": DiyaLoop,
    "cosmic_sky": CosmicSky,
    "story_panels": StoryPanels,
    "split_meaning": SplitMeaning,
}

def get_strategy(name: str) -> Strategy:
    return STRATEGIES.get(name, DiyaLoop)()