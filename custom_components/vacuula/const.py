"""Constants for the Vacuula integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "vacuula"
PLATFORMS: list[Platform] = [Platform.VACUUM]

DEFAULT_URL = "http://vacuula.lan"
DEFAULT_SCAN_INTERVAL = 60

# Robot generation identifiers returned by GET /api/robots
ROBOT_TYPE_GEN3 = "neato.gen3"
ROBOT_TYPE_GEN4 = "neato.gen4"

# Gen3 cleaning parameters
GEN3_CATEGORY_HOUSE = 2
GEN3_CATEGORY_SPOT = 3
GEN3_CATEGORY_MAP = 4

GEN3_MODE_ECO = 1
GEN3_MODE_TURBO = 2

GEN3_NAV_NORMAL = 1
GEN3_NAV_EXTRA_CARE = 2
GEN3_NAV_DEEP = 3

FAN_SPEED_ECO = "eco"
FAN_SPEED_TURBO = "turbo"
FAN_SPEEDS = [FAN_SPEED_ECO, FAN_SPEED_TURBO]
