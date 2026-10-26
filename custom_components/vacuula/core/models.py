"""Pure-Python data models and state normalization for Vacuula robots."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .const import (
    ALL_ZONES_OPTION,
    CLEAN_CATEGORY_HOUSE,
    CLEAN_CATEGORY_MAP,
    FAN_SPEED_ECO,
    FAN_SPEED_TURBO,
    GEN3_ACTION_DOCKING,
    GEN3_ACTION_NAMES,
    GEN3_CATEGORY_HOUSE,
    GEN3_CATEGORY_MAP,
    GEN3_MODE_ECO,
    GEN3_NAV_CODE_TO_NAME,
    GEN3_STATE_BUSY,
    GEN3_STATE_ERROR,
    GEN3_STATE_IDLE,
    GEN3_STATE_PAUSED,
    NAV_MODE_NORMAL,
    ROBOT_TYPE_GEN3,
)
from .map_renderer import compute_cropped_zones

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-b(\d+))?$")


def parse_installer_version(v: str) -> tuple[int, int, int, float]:
    """Parse an X.Y.Z[-bN] installer version string into a comparable tuple."""
    m = _VERSION_RE.match(v.strip())
    if not m:
        return (-999, -999, -999, float("-inf"))
    major, minor, patch, beta = m.groups()
    beta_rank = int(beta) if beta is not None else float("inf")
    return (int(major), int(minor), int(patch), beta_rank)


def is_installer_outdated(
    installed_with: str | None, min_version: str | None = "1.1.0-b3"
) -> bool:
    """Return True if installed_with is older than min_version."""
    if not installed_with or "dev" in installed_with:
        return False
    target_min = min_version or "1.1.0-b3"
    return parse_installer_version(installed_with) < parse_installer_version(target_min)


def did_finish_cleaning(
    robot_type: str, old_state: dict[str, Any], new_state: dict[str, Any]
) -> bool:
    """Return True if the robot just transitioned from BUSY to IDLE."""
    if not old_state or not new_state:
        return False
    if robot_type == ROBOT_TYPE_GEN3:
        return (
            old_state.get("state") == GEN3_STATE_BUSY
            and new_state.get("state") == GEN3_STATE_IDLE
        )
    old_body = old_state.get("body", old_state)
    new_body = new_state.get("body", new_state)
    return (
        isinstance(old_body, dict)
        and isinstance(new_body, dict)
        and str(old_body.get("state", "")).lower() == "busy"
        and str(new_body.get("state", "")).lower() == "idle"
    )


@dataclass
class VacuulaRobotData:
    """Aggregated metadata, live state, maps, zones, and preferences for a single robot."""

    serial: str
    name: str
    robot_type: str
    connected: bool
    state: dict[str, Any] = field(default_factory=dict)
    preferred_fan_speed: str = FAN_SPEED_TURBO
    preferred_navigation_mode: str = NAV_MODE_NORMAL
    preferred_category: int = GEN3_CATEGORY_MAP
    selected_zone: str = ALL_ZONES_OPTION
    maps: list[dict[str, Any]] = field(default_factory=list)
    active_map_id: str | None = None
    active_map_name: str | None = None
    floormap: dict[str, Any] | None = None
    boundaries: list[dict[str, Any]] = field(default_factory=list)
    zones: list[dict[str, Any]] = field(default_factory=list)
    last_run: dict[str, Any] | None = None
    last_run_id: str | None = None
    last_runmap: dict[str, Any] | None = None
    total_runs: int = 0
    maps_loaded: bool = False
    installed_with: str | None = None

    def sync_preferences_from_state(self) -> None:
        """Seed cleaning preferences from robot state when available."""
        if self.robot_type == ROBOT_TYPE_GEN3 and self.state:
            cleaning = self.state.get("cleaning") or {}
            mode = cleaning.get("mode")
            if mode is not None:
                self.preferred_fan_speed = (
                    FAN_SPEED_ECO if mode == GEN3_MODE_ECO else FAN_SPEED_TURBO
                )
            nav_code = cleaning.get("navigationMode")
            if nav_code in GEN3_NAV_CODE_TO_NAME:
                self.preferred_navigation_mode = GEN3_NAV_CODE_TO_NAME[nav_code]
            category = cleaning.get("category")
            if category in (GEN3_CATEGORY_HOUSE, GEN3_CATEGORY_MAP):
                self.preferred_category = category

    def resolve_zone_ids(self, zone_names_or_ids: list[str]) -> list[str]:
        """Resolve a list of room names (case-insensitive) or boundary UUIDs to boundary IDs."""
        by_id = {str(z.get("id")): str(z.get("id")) for z in self.zones if z.get("id")}
        by_name = {
            str(z.get("name", "")).strip().lower(): str(z.get("id"))
            for z in self.zones
            if z.get("id") and z.get("name")
        }
        resolved: list[str] = []
        for item in zone_names_or_ids:
            token = item.strip()
            if not token:
                continue
            if token in by_id:
                resolved.append(by_id[token])
            elif token.lower() in by_name:
                resolved.append(by_name[token.lower()])
            else:
                resolved.append(token)
        return resolved

    @property
    def activity_state(self) -> str:
        """Return normalized vacuum activity string ('docked', 'cleaning', 'paused', 'returning', 'error', 'idle')."""
        if not self.state:
            return "idle"
        if self.robot_type == ROBOT_TYPE_GEN3:
            if self.state.get("error"):
                return "error"
            code = self.state.get("state")
            action = self.state.get("action")
            details = self.state.get("details") or {}
            if code == GEN3_STATE_ERROR:
                return "error"
            if action == GEN3_ACTION_DOCKING:
                return "returning"
            if code == GEN3_STATE_BUSY:
                return "cleaning"
            if code == GEN3_STATE_PAUSED:
                return "paused"
            if details.get("isDocked"):
                return "docked"
            return "idle"

        body = self.state.get("body", self.state)
        if not isinstance(body, dict):
            return "idle"
        if body.get("error"):
            return "error"
        raw = str(body.get("state", "")).lower()
        action = str(body.get("action", "")).lower()
        if "error" in raw or "fault" in raw:
            return "error"
        if "dock" in action or "return" in action or raw == "returning":
            return "returning"
        if raw in ("busy", "cleaning", "working"):
            return "cleaning"
        if raw == "paused":
            return "paused"
        if body.get("is_docked") or body.get("docked") or raw == "docked":
            return "docked"
        return "idle"

    @property
    def battery_level(self) -> int | None:
        """Return battery percentage (0..100) if available."""
        if not self.state:
            return None
        if self.robot_type == ROBOT_TYPE_GEN3:
            charge = (self.state.get("details") or {}).get("charge")
            return int(charge) if isinstance(charge, (int, float)) else None
        body = self.state.get("body", self.state)
        if isinstance(body, dict):
            val = body.get("battery_level", body.get("charge"))
            return int(val) if isinstance(val, (int, float)) else None
        return None

    @property
    def is_docked(self) -> bool:
        """Return True if robot is docked."""
        if self.robot_type == ROBOT_TYPE_GEN3:
            return bool((self.state.get("details") or {}).get("isDocked"))
        body = self.state.get("body", self.state)
        return bool(
            isinstance(body, dict) and (body.get("is_docked") or body.get("docked"))
        )

    @property
    def is_charging(self) -> bool:
        """Return True if robot is charging."""
        if self.robot_type == ROBOT_TYPE_GEN3:
            return bool((self.state.get("details") or {}).get("isCharging"))
        body = self.state.get("body", self.state)
        return bool(
            isinstance(body, dict) and (body.get("is_charging") or body.get("charging"))
        )

    @property
    def current_action_name(self) -> str:
        """Return human-readable action code name."""
        if self.robot_type == ROBOT_TYPE_GEN3:
            act = int(self.state.get("action", 0) or 0)
            return GEN3_ACTION_NAMES.get(act, f"action_{act}")
        body = self.state.get("body", self.state)
        if isinstance(body, dict) and body.get("action"):
            return str(body["action"])
        return "idle"

    def to_snapshot(
        self, min_installer_version: str | None = "1.1.0-b3"
    ) -> dict[str, Any]:
        """Return a JSON-serializable state snapshot suitable for the standalone web sandbox or CLI."""
        cropped_zones = compute_cropped_zones(self.floormap, self.boundaries)
        clean_cat = (
            CLEAN_CATEGORY_HOUSE
            if self.preferred_category == GEN3_CATEGORY_HOUSE
            else CLEAN_CATEGORY_MAP
        )
        return {
            "serial": self.serial,
            "name": self.name,
            "robot_type": self.robot_type,
            "connected": self.connected,
            "activity": self.activity_state,
            "action": self.current_action_name,
            "battery_level": self.battery_level,
            "is_docked": self.is_docked,
            "is_charging": self.is_charging,
            "fan_speed": self.preferred_fan_speed,
            "navigation_mode": self.preferred_navigation_mode,
            "clean_category": clean_cat,
            "selected_zone": self.selected_zone,
            "active_map_id": self.active_map_id,
            "active_map_name": self.active_map_name,
            "maps": [
                {"id": m.get("id"), "name": m.get("name")}
                for m in self.maps
                if m.get("id")
            ],
            "zones": cropped_zones,
            "raw_zones": self.zones,
            "boundaries": self.boundaries,
            "total_runs": self.total_runs,
            "last_run": self.last_run,
            "error": self.state.get("error") if self.state else None,
            "alert": self.state.get("alert") if self.state else None,
            "schedule_enabled": bool(
                (self.state.get("details") or {}).get("isScheduleEnabled")
            )
            if self.robot_type == ROBOT_TYPE_GEN3
            else False,
            "installed_with": self.installed_with,
            "installer_outdated": is_installer_outdated(
                self.installed_with, min_installer_version
            ),
        }
