"""Pytest path setup for the plugin test suite."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ASTRBOT_ROOT = PLUGIN_ROOT.parents[2]
PLUGIN_NAME = "astrbot_plugin_tool_guard"

for path in (str(ASTRBOT_ROOT), str(PLUGIN_ROOT.parent)):
    if path not in sys.path:
        sys.path.insert(0, path)

if PLUGIN_NAME not in sys.modules:
    package = types.ModuleType(PLUGIN_NAME)
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules[PLUGIN_NAME] = package

for module_name in ("auth", "matcher", "runtime", "request_filter", "tool_block"):
    full_name = f"{PLUGIN_NAME}.{module_name}"
    if full_name not in sys.modules:
        importlib.import_module(full_name)
    sys.modules[module_name] = sys.modules[full_name]
