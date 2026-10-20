"""Load the pure modules without importing Home Assistant (the package __init__ needs it)."""

from __future__ import annotations

from pathlib import Path
import sys
import types

_PACKAGE = "awtrix_pure"
_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "awtrix"

if _PACKAGE not in sys.modules:
    package = types.ModuleType(_PACKAGE)
    package.__path__ = [str(_DIR)]
    sys.modules[_PACKAGE] = package

from awtrix_pure import const, discovery, messages, results, translate

__all__ = ["const", "discovery", "messages", "results", "translate"]
