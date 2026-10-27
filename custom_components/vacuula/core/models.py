"""Pure-Python data models and state normalization for Vacuula robots."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .const import (
    ALL_ZONES_OPTION,
    CLEAN_CATEGORY_HOUSE,
    CLEAN_CATEGORY_MAP,
    FAN_SPEED_ECO,
    FAN_SPEED_TURBO,
    GEN3_ACTION_DOCKING,
    GEN3_ACTION_NAMES,
    GEN3_ACTION_SUSPENDED_CLEANING,
    GEN3_ACTION_SUSPENDED_EXPLORATION,
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
    preferred_map_id: str | None = None
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
    _cropped_zones_key: tuple[Any, ...] | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _cropped_zones_val: list[dict[str, Any]] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    @property
    def gen4_body(self) -> dict[str, Any]:
        """Return the inner body dictionary for a Gen4 robot state."""
        if not self.state:
            return {}
        body = self.state.get("body")
        return body if isinstance(body, dict) else self.state

    @property
    def boundary_signature(self) -> tuple[Any, ...]:
        """Return a fast hashable signature of current room boundaries."""
        if not self.boundaries:
            return ()
        return tuple(
            (
                b.get("id"),
                b.get("name"),
                b.get("color"),
                len(b.get("vertices") or ()),
            )
            for b in self.boundaries
            if isinstance(b, dict)
        )

    @property
    def cropped_zones(self) -> list[dict[str, Any]]:
        """Return cropped zones normalized to [0..1], cached across state updates."""
        if not self.floormap or not self.boundaries:
            return []
        rle = self.floormap.get("rle")
        key = (
            self.active_map_id,
            id(self.floormap),
            len(rle) if isinstance(rle, list) else 0,
            self.boundary_signature,
        )
        if self._cropped_zones_key != key:
            self._cropped_zones_val = compute_cropped_zones(
                self.floormap, self.boundaries
            )
            self._cropped_zones_key = key
        return self._cropped_zones_val

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
            state_code = self.state.get("state")
            action_code = self.state.get("action", 0)
            details = self.state.get("details") or {}
            if state_code == GEN3_STATE_ERROR or self.state.get("error"):
                return "error"
            if action_code == GEN3_ACTION_DOCKING:
                return "returning"
            if state_code == GEN3_STATE_PAUSED:
                return "paused"
            if state_code == GEN3_STATE_BUSY:
                if action_code in (
                    GEN3_ACTION_SUSPENDED_CLEANING,
                    GEN3_ACTION_SUSPENDED_EXPLORATION,
                ):
                    return "docked" if details.get("isDocked") else "paused"
                return "cleaning"
            if state_code == GEN3_STATE_IDLE:
                return "docked" if details.get("isDocked") else "idle"
            return "idle"

        body = self.gen4_body
        state_str = str(body.get("state", "")).lower()
        action_str = str(body.get("action", "")).lower()
        details = body.get("details") or {}
        errors = body.get("errors")

        if (
            body.get("error")
            or "error" in state_str
            or "fault" in state_str
            or (isinstance(errors, list) and len(errors) > 0)
        ):
            return "error"
        if state_str == "paused":
            return "paused"
        if (
            action_str == "docking"
            or "return" in action_str
            or state_str == "returning"
        ):
            return "returning"
        if state_str in ("busy", "cleaning", "working"):
            return "cleaning"
        if (
            details.get("is_docked")
            or details.get("isDocked")
            or body.get("is_docked")
            or body.get("docked")
            or state_str == "docked"
        ):
            return "docked"
        return "idle"

    @property
    def battery_level(self) -> int | None:
        """Return battery percentage (0..100) if available."""
        if not self.state:
            return None
        if self.robot_type == ROBOT_TYPE_GEN3:
            val = (self.state.get("details") or {}).get("charge")
        else:
            body = self.gen4_body
            details = body.get("details") or {}
            val = details.get("charge", body.get("battery_level", body.get("charge")))
        if val is None or isinstance(val, bool):
            return None
        try:
            return round(float(val))
        except TypeError, ValueError:
            return None

    @property
    def is_docked(self) -> bool:
        """Return True if robot is docked."""
        if not self.state:
            return False
        if self.robot_type == ROBOT_TYPE_GEN3:
            return bool((self.state.get("details") or {}).get("isDocked"))
        body = self.gen4_body
        details = body.get("details") or {}
        return bool(
            details.get("is_docked")
            or details.get("isDocked")
            or body.get("is_docked")
            or body.get("docked")
        )

    @property
    def is_charging(self) -> bool:
        """Return True if robot is charging."""
        if not self.state:
            return False
        if self.robot_type == ROBOT_TYPE_GEN3:
            return bool((self.state.get("details") or {}).get("isCharging"))
        body = self.gen4_body
        details = body.get("details") or {}
        return bool(
            details.get("is_charging")
            or details.get("isCharging")
            or body.get("is_charging")
            or body.get("charging")
        )

    @property
    def dock_has_been_seen(self) -> bool | None:
        """Return True if a Gen3 robot has seen its charging base."""
        if not self.state:
            return None
        return bool((self.state.get("details") or {}).get("dockHasBeenSeen"))

    @property
    def is_schedule_enabled(self) -> bool | None:
        """Return True if the robot's internal schedule is enabled."""
        if not self.state:
            return None
        return bool((self.state.get("details") or {}).get("isScheduleEnabled", False))

    @property
    def current_action_name(self) -> str:
        """Return human-readable action code name."""
        if not self.state:
            return "idle"
        if self.robot_type == ROBOT_TYPE_GEN3:
            act = int(self.state.get("action", 0) or 0)
            return GEN3_ACTION_NAMES.get(act, f"unknown_{act}")
        body = self.gen4_body
        return str(body.get("action") or "idle").lower()

    @property
    def alert_or_error(self) -> str:
        """Return active error/alert code or 'none'."""
        if not self.state:
            return "none"
        if self.robot_type == ROBOT_TYPE_GEN3:
            err = self.state.get("error")
            alert = self.state.get("alert")
            return str(err or alert or "none")
        errors = self.gen4_body.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict) and first.get("code"):
                return str(first["code"])
        return "none"

    @property
    def is_bin_full(self) -> bool | None:
        """Return True if the dust bin is full or missing."""
        if not self.state:
            return None
        if self.robot_type == ROBOT_TYPE_GEN3:
            alert = str(self.state.get("alert") or "").lower()
            error = str(self.state.get("error") or "").lower()
            return "dustbin" in alert or "dustbin" in error
        errors = self.gen4_body.get("errors") or []
        if isinstance(errors, list):
            for err in errors:
                if isinstance(err, dict):
                    code = str(err.get("code") or "").lower()
                    if "dustbin" in code or "bin_full" in code:
                        return True
        return False

    @property
    def last_clean_area_m2(self) -> float | None:
        """Return area cleaned during the most recent run in square meters."""
        if not self.last_run:
            return None
        area = self.last_run.get("area") or self.last_run.get("cleaned_area")
        if isinstance(area, (int, float)):
            val = float(area)
            if val > 500:
                val = val / 10000.0
            return round(val, 2)
        return None

    @property
    def last_clean_duration_min(self) -> float | None:
        """Return duration of the most recent cleaning run in minutes."""
        if not self.last_run:
            return None
        dur = self.last_run.get("duration")
        if isinstance(dur, (int, float)):
            return round(float(dur) / 60.0, 1)
        start_str = self.last_run.get("start_at") or self.last_run.get("started_at")
        end_str = self.last_run.get("end_at") or self.last_run.get("ended_at")
        if isinstance(start_str, str) and isinstance(end_str, str):
            try:
                t0 = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                return round(max(0.0, (t1 - t0).total_seconds() / 60.0), 1)
            except ValueError:
                return None
        return None

    def to_snapshot(
        self, min_installer_version: str | None = "1.1.0-b3"
    ) -> dict[str, Any]:
        """Return a JSON-serializable state snapshot suitable for the standalone web sandbox or CLI."""
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
            "zones": self.cropped_zones,
            "raw_zones": self.zones,
            "boundaries": self.boundaries,
            "total_runs": self.total_runs,
            "last_run": self.last_run,
            "error": self.state.get("error") if self.state else None,
            "alert": self.state.get("alert") if self.state else None,
            "schedule_enabled": bool(self.is_schedule_enabled)
            if self.robot_type == ROBOT_TYPE_GEN3
            else False,
            "installed_with": self.installed_with,
            "installer_outdated": is_installer_outdated(
                self.installed_with, min_installer_version
            ),
        }
