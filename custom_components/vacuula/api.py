"""Async API client for Vacuula Server (Gen3 & Gen4 robots) with per-robot locking and SSE."""

from __future__ import annotations

from .core.client import VacuulaApiClient, _seg
from .core.exceptions import (
    VacuulaApiError,
    VacuulaAuthError,
    VacuulaConnectionError,
)

__all__ = [
    "VacuulaApiClient",
    "VacuulaApiError",
    "VacuulaAuthError",
    "VacuulaConnectionError",
    "_seg",
]
