"""Standalone async Python SDK for Vacuula Server (Zero Home Assistant dependencies).

Exposes the pure-Python core SDK from custom_components.vacuula.core without
requiring Home Assistant to be installed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Locate custom_components/vacuula/core directly on disk so importing `aiovacuula`
# never triggers `custom_components/vacuula/__init__.py` (which imports homeassistant).
_CORE_DIR = (
    Path(__file__).resolve().parents[4] / "custom_components" / "vacuula" / "core"
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

from custom_components.vacuula.core import (  # noqa: E402
    ALL_ZONES_OPTION,
    CLEAN_CATEGORY_HOUSE,
    CLEAN_CATEGORY_MAP,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_URL,
    DEFAULT_VACUULA_PORT,
    DOMAIN,
    FAN_SPEED_ECO,
    FAN_SPEED_TURBO,
    FAN_SPEEDS_GEN3,
    FAN_SPEEDS_GEN4,
    GEN3_ACTION_ACQUIRING_MAP_IDS,
    GEN3_ACTION_COPYING_LOGS,
    GEN3_ACTION_CREATING_MAP,
    GEN3_ACTION_DOCKING,
    GEN3_ACTION_EXPLORING_MAP,
    GEN3_ACTION_HOUSE_CLEANING,
    GEN3_ACTION_IEC_TEST,
    GEN3_ACTION_MANUAL_CLEANING,
    GEN3_ACTION_MAP_CLEANING,
    GEN3_ACTION_NAMES,
    GEN3_ACTION_NONE,
    GEN3_ACTION_RECOVERING_LOCATION,
    GEN3_ACTION_SPOT_CLEANING,
    GEN3_ACTION_SUSPENDED_CLEANING,
    GEN3_ACTION_SUSPENDED_EXPLORATION,
    GEN3_ACTION_UPDATING,
    GEN3_ACTION_USER_MENU,
    GEN3_CATEGORY_HOUSE,
    GEN3_CATEGORY_MANUAL,
    GEN3_CATEGORY_MAP,
    GEN3_CATEGORY_SPOT,
    GEN3_CLEAN_CATEGORIES,
    GEN3_MODE_ECO,
    GEN3_MODE_TURBO,
    GEN3_NAV_CODE_TO_NAME,
    GEN3_NAV_MODE_TO_CODE,
    GEN3_NAV_MODES,
    GEN3_STATE_BUSY,
    GEN3_STATE_ERROR,
    GEN3_STATE_IDLE,
    GEN3_STATE_INVALID,
    GEN3_STATE_PAUSED,
    GEN4_NAV_MODES,
    NAV_MODE_DEEP,
    NAV_MODE_EXTRA_CARE,
    NAV_MODE_GENTLE,
    NAV_MODE_NORMAL,
    ROBOT_TYPE_GEN3,
    ROBOT_TYPE_GEN4,
    SERVICE_CLEAN_SPOT,
    SERVICE_CLEAN_ZONES,
    SERVICE_REFRESH_MAPS,
    VacuulaApiClient,
    VacuulaApiError,
    VacuulaAuthError,
    VacuulaConnectionError,
    VacuulaController,
    VacuulaRobotData,
    compute_cropped_zones,
    did_finish_cleaning,
    get_crop_box,
    is_installer_outdated,
    parse_installer_version,
    render_map_png,
)

__all__ = [
    "ALL_ZONES_OPTION",
    "CLEAN_CATEGORY_HOUSE",
    "CLEAN_CATEGORY_MAP",
    "DEFAULT_SCAN_INTERVAL",
    "DEFAULT_URL",
    "DEFAULT_VACUULA_PORT",
    "DOMAIN",
    "FAN_SPEEDS_GEN3",
    "FAN_SPEEDS_GEN4",
    "FAN_SPEED_ECO",
    "FAN_SPEED_TURBO",
    "GEN3_ACTION_ACQUIRING_MAP_IDS",
    "GEN3_ACTION_COPYING_LOGS",
    "GEN3_ACTION_CREATING_MAP",
    "GEN3_ACTION_DOCKING",
    "GEN3_ACTION_EXPLORING_MAP",
    "GEN3_ACTION_HOUSE_CLEANING",
    "GEN3_ACTION_IEC_TEST",
    "GEN3_ACTION_MANUAL_CLEANING",
    "GEN3_ACTION_MAP_CLEANING",
    "GEN3_ACTION_NAMES",
    "GEN3_ACTION_NONE",
    "GEN3_ACTION_RECOVERING_LOCATION",
    "GEN3_ACTION_SPOT_CLEANING",
    "GEN3_ACTION_SUSPENDED_CLEANING",
    "GEN3_ACTION_SUSPENDED_EXPLORATION",
    "GEN3_ACTION_UPDATING",
    "GEN3_ACTION_USER_MENU",
    "GEN3_CATEGORY_HOUSE",
    "GEN3_CATEGORY_MANUAL",
    "GEN3_CATEGORY_MAP",
    "GEN3_CATEGORY_SPOT",
    "GEN3_CLEAN_CATEGORIES",
    "GEN3_MODE_ECO",
    "GEN3_MODE_TURBO",
    "GEN3_NAV_CODE_TO_NAME",
    "GEN3_NAV_MODES",
    "GEN3_NAV_MODE_TO_CODE",
    "GEN3_STATE_BUSY",
    "GEN3_STATE_ERROR",
    "GEN3_STATE_IDLE",
    "GEN3_STATE_INVALID",
    "GEN3_STATE_PAUSED",
    "GEN4_NAV_MODES",
    "NAV_MODE_DEEP",
    "NAV_MODE_EXTRA_CARE",
    "NAV_MODE_GENTLE",
    "NAV_MODE_NORMAL",
    "ROBOT_TYPE_GEN3",
    "ROBOT_TYPE_GEN4",
    "SERVICE_CLEAN_SPOT",
    "SERVICE_CLEAN_ZONES",
    "SERVICE_REFRESH_MAPS",
    "VacuulaApiClient",
    "VacuulaApiError",
    "VacuulaAuthError",
    "VacuulaConnectionError",
    "VacuulaController",
    "VacuulaRobotData",
    "compute_cropped_zones",
    "did_finish_cleaning",
    "get_crop_box",
    "is_installer_outdated",
    "parse_installer_version",
    "render_map_png",
]
