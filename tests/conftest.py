import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
"""Test stubs so the render slice can be tested where keyring/httpx/edge_tts are not installed."""
import sys, types
for name in ("keyring", "httpx", "edge_tts"):
    try:
        __import__(name)
    except ImportError:
        m = types.ModuleType(name)
        if name == "keyring":
            m.get_password = lambda *a, **k: None
            m.set_password = lambda *a, **k: None
            m.delete_password = lambda *a, **k: None
        sys.modules[name] = m
