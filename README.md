# Vacuula Home Assistant Integration (`hass-vacuula`)

Custom [Home Assistant](https://www.home-assistant.io/) integration (HACS-compatible) for [Vacuula](https://github.com/vacuula/vacuula) — the local replacement cloud server for Neato Botvac Connected (Gen3: D3–D7, Gen4: D800/D8–D10) robot vacuums.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design outline, API specification, and Gen3/Gen4 protocol mapping.

## Features
- **Auto-Discovery & Manual Setup**: Automatically discovers your Vacuula server on the LAN via mDNS (`_vacuula._tcp.local.`) with confirmation, or connects via URL (e.g., `http://vacuula.lan`).
- **Bundled Interactive Lovelace Map Card (`custom:vacuula-map-card`)**: Automatically registered in Home Assistant's frontend when the integration loads — no separate HACS frontend installation or manual resource setup needed! Features:
  - Interactive floor plan with clickable SVG room polygons and floating room pins right on the map.
  - Multi-room selection: tap one or more rooms on the map (or via the room chips bar) and press **Clean N Rooms** to trigger a multi-room zone clean.
  - One-click toggle between **Floor Plan** and **Last Run** coverage map.
  - Built-in controls for Start/Resume, Pause, Stop, Return to Dock, Locate, Fan Speed (`Eco`/`Turbo`), and Navigation Mode (`Normal`/`Extra Care`/`Deep`).
  - Full visual card editor inside Home Assistant's **+ Add Card** dialog.
- **Real-Time SSE Push + Fallback Polling**: Subscribes to `/api/events` and `/api/robot/{serial}/connect` Server-Sent Events for instant state updates and dynamic discovery of newly connected robots, backed by concurrent 30-second fallback polling.
- **Multi-Robot & Multi-Generation**: Supports both **Gen3** (`D3`, `D4`, `D5`, `D6`, `D7`) and **Gen4** (`D800`, `D8`, `D9`, `D10`) Neato robots managed by a single Vacuula server, with per-robot `asyncio.Lock` command serialization.
- **Live Floor Map & Last Run Map Rendering (`image.*`)**: Pure-Python RLE-to-PNG renderer (`map_renderer.py`, zero external dependencies) rendering walls, floor space, colored room zones, No-Go lines, charging dock marker, and last cleaning run coverage.

## Dashboard Card Usage

Once the integration is loaded, open any Home Assistant dashboard, click **Edit → + Add Card**, and select **Vacuula Map & Room Card** from the card picker, or use YAML:

```yaml
type: custom:vacuula-map-card
entity: vacuum.mappa
default_view: floor
show_zone_labels: true
show_controls: true
```

See [`dashboards/vacuula_dashboard_card.yaml`](dashboards/vacuula_dashboard_card.yaml) for both the `custom:vacuula-map-card` configuration and a pure native Home Assistant card stack.

## Complete Entity Suite per Robot
- **`vacuum.<name>`**: Start (full map/house or selected target room zone), Pause, Resume, Stop, Return to Base, Locate (`findMe`), and Fan Speed (`eco` / `turbo`).
- **`image.<name>_floor_map`**: Rendered PNG of the active floor plan with colored room zones, No-Go lines, dock location, and normalized room polygon coordinates.
- **`image.<name>_last_run_map`**: Rendered PNG of the most recent cleaning run overlaid on the floor plan.
- **`sensor.<name>_battery`**: Battery level (`%`, `SensorDeviceClass.BATTERY`).
- **`sensor.<name>_action`**: Current robot action (`house_cleaning`, `map_cleaning`, `docking`, `suspended_cleaning`, `idle`, etc.).
- **`sensor.<name>_alert`**: Active alert or error code (`dustbin_full`, `clean_completed_to_start`, etc., or `none`).
- **`sensor.<name>_last_clean_area`**: Cleaned area of the last run (`m²`, `SensorDeviceClass.AREA`).
- **`sensor.<name>_last_clean_duration`**: Duration of the last run (`min`, `SensorDeviceClass.DURATION`).
- **`sensor.<name>_total_cleans`**: Total historical cleaning runs recorded in Vacuula (`SensorStateClass.TOTAL_INCREASING`).
- **`binary_sensor.<name>_docked`**: Dock connection status (`BinarySensorDeviceClass.PLUG`).
- **`binary_sensor.<name>_charging`**: Battery charging status (`BinarySensorDeviceClass.BATTERY_CHARGING`).
- **`binary_sensor.<name>_dock_seen`**: Whether the robot has seen its charging base (Gen3).
- **`button.<name>_locate`**: Trigger `findMe` beep.
- **`button.<name>_dismiss_alert`**: Dismiss active robot alert (`dismissCurrentAlert` on Gen3).
- **`button.<name>_refresh_maps`**: Reload floor maps, room boundaries, and run history from Vacuula.
- **`button.<name>_explore_new_map`**: Start persistent map exploration (`startPersistentMapExploration`).
- **`button.<name>_clean_<room>`**: Dynamic one-tap button created for every room zone defined on the active floor plan.
- **`switch.<name>_schedule`**: Enable or disable the robot's internal cleaning schedule (Gen3).
- **`select.<name>_navigation_mode`**: Select navigation mode (`normal`, `extra_care`, `deep` on Gen3; `normal`, `gentle` on Gen4).
- **`select.<name>_cleaning_mode`**: Select Gen3 cleaning category (`map` with persistent floor plan & No-Go lines vs `house`).
- **`select.<name>_target_zone`**: Select `"all"` (entire map) or a specific room name for the next `vacuum.start` command.

## Custom Actions (`services.yaml`)
```yaml
# Clean one or more rooms by name (case-insensitive) or boundary UUID
action: vacuula.clean_zones
data:
  zones:
    - Diningroom
    - Hallway
  fan_speed: turbo
  navigation_mode: normal

# Clean a 200x200 cm spot (Gen3)
action: vacuula.clean_spot
data:
  width: 200
  height: 200
  fan_speed: turbo
```

## Installation into Home Assistant (`home`)
To deploy directly to your Home Assistant server on `home`:
```bash
scp -r /home/abewi/hass-vacuula/custom_components/vacuula home:~/docker-images/home-assistant/config/custom_components/
ssh home "sudo docker restart homeassistant"
```
Then in Home Assistant, go to **Settings → Devices & Services → Add Integration → Vacuula** and enter `http://vacuula.lan` (or `http://172.18.0.1:8085`).
