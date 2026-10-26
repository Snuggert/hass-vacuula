"""Constants for the Vacuula integration."""

from __future__ import annotations

try:
    from homeassistant.const import Platform

    PLATFORMS: list[Platform] = [
        Platform.VACUUM,
        Platform.SENSOR,
        Platform.BINARY_SENSOR,
        Platform.BUTTON,
        Platform.SWITCH,
        Platform.SELECT,
        Platform.IMAGE,
    ]
except ImportError:  # pragma: no cover
    PLATFORMS = []  # type: ignore[assignment]

from .core import const as _core_const
from .core.const import *  # noqa: F403

__all__ = ["PLATFORMS", *(k for k in dir(_core_const) if k.isupper())]
