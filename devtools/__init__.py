"""Developer tools, live server harness, mock Neato hardware, and zero-HA core loader."""

from __future__ import annotations

from typing import Any

__all__ = [
    "MockNeatoRobot",
    "VacuulaDevSandbox",
    "VacuulaServerManager",
    "build_sample_floormap_rle",
    "build_sample_runmap_rle",
]


def __getattr__(name: str) -> Any:
    """Lazy-load devtools components so `import devtools.core` has zero HA dependencies."""
    if name in (
        "MockNeatoRobot",
        "build_sample_floormap_rle",
        "build_sample_runmap_rle",
    ):
        from . import mock_neato

        return getattr(mock_neato, name)
    if name == "VacuulaServerManager":
        from .server_manager import VacuulaServerManager

        return VacuulaServerManager
    if name == "VacuulaDevSandbox":
        from .sandbox import VacuulaDevSandbox

        return VacuulaDevSandbox
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
