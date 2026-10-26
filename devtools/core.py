"""Standalone async Python SDK for Vacuula Server (Zero Home Assistant dependencies).

Exposes the pure-Python core SDK from custom_components.vacuula.core without
requiring Home Assistant to be installed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Locate custom_components/vacuula/core directly on disk so importing `devtools.core`
# never triggers `custom_components/vacuula/__init__.py` (which imports homeassistant).
_CORE_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "vacuula" / "core"
)
if _CORE_DIR.is_dir() and "custom_components.vacuula.core" not in sys.modules:
    for _mod_name, _file_name in (
        ("custom_components.vacuula.core.exceptions", "exceptions.py"),
        ("custom_components.vacuula.core.const", "const.py"),
        ("custom_components.vacuula.core.map_renderer", "map_renderer.py"),
        ("custom_components.vacuula.core.client", "client.py"),
        ("custom_components.vacuula.core.models", "models.py"),
        ("custom_components.vacuula.core.controller", "controller.py"),
        ("custom_components.vacuula.core", "__init__.py"),
    ):
        if _mod_name not in sys.modules:
            _spec = importlib.util.spec_from_file_location(
                _mod_name,
                _CORE_DIR / _file_name,
                submodule_search_locations=[str(_CORE_DIR)]
                if _file_name == "__init__.py"
                else None,
            )
            if _spec and _spec.loader:
                _module = importlib.util.module_from_spec(_spec)
                sys.modules[_mod_name] = _module
                _spec.loader.exec_module(_module)

from custom_components.vacuula.core import *  # noqa: E402, F403

__all__ = list(sys.modules["custom_components.vacuula.core"].__all__)
