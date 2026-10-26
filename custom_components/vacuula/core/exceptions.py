"""Exceptions for the Vacuula core SDK and integration."""

from __future__ import annotations

try:
    from homeassistant.exceptions import HomeAssistantError as _BaseError
except ImportError:  # pragma: no cover
    _BaseError = Exception  # type: ignore[assignment,misc]


class VacuulaApiError(_BaseError):
    """Exception raised for Vacuula API errors."""


class VacuulaAuthError(VacuulaApiError):
    """Exception raised when authentication with Vacuula server fails."""


class VacuulaConnectionError(VacuulaApiError):
    """Exception raised when HTTP or socket transport fails."""
