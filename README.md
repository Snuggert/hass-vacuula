# Vacuula Home Assistant Integration (`hass-vacuula`)

Custom [Home Assistant](https://www.home-assistant.io/) integration (HACS-compatible) for [Vacuula](https://github.com/vacuula/vacuula) — the local replacement cloud server for Neato Botvac Connected (Gen3: D3–D7, Gen4: D800/D8–D10) robot vacuums.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design outline, API specification, and Gen3/Gen4 protocol mapping.

## Features
- **Auto-Discovery & Manual Setup**: Automatically discovers your Vacuula server on the LAN via mDNS (`_vacuula._tcp.local.`) with confirmation, or connects via URL (e.g., `http://vacuula.lan`).
- **Real-Time SSE Push + Fallback Polling**: Subscribes to `/api/events` and `/api/robot/{serial}/connect` Server-Sent Events for instant state updates and dynamic discovery of newly connected robots, backed by concurrent 30-second fallback polling.
- **Multi-Robot & Multi-Generation**: Supports both **Gen3** (`D3`, `D4`, `D5`, `D6`, `D7`) and **Gen4** (`D800`, `D8`, `D9`, `D10`) Neato robots managed by a single Vacuula server, with per-robot `asyncio.Lock` command serialization.
- **Complete Entity Suite per Robot**:
  - `vacuum.<name>`: Start (uses persistent map + No-Go lines `category=4` on Gen3 by default), Pause, Resume, Stop, Return to Base, Locate (`findMe`), and Fan Speed (`eco` / `turbo`).
  - `sensor.<name>_battery`: Dedicated `%` battery sensor (`SensorDeviceClass.BATTERY`).
  - `sensor.<name>_action`: Current robot action (`house_cleaning`, `docking`, `suspended_cleaning`, `idle`, etc.).
  - `sensor.<name>_alert`: Active alert or error code (`dustbin_full`, `clean_completed_to_start`, etc., or `none`).
  - `binary_sensor.<name>_docked`: Dock connection status (`BinarySensorDeviceClass.PLUG`).
  - `binary_sensor.<name>_charging`: Battery charging status (`BinarySensorDeviceClass.BATTERY_CHARGING`).
  - `button.<name>_locate`: Trigger `findMe` beep.
  - `button.<name>_dismiss_alert`: Dismiss active robot alert (`dismissCurrentAlert` on Gen3).
  - `switch.<name>_schedule`: Enable or disable the robot's internal cleaning schedule (Gen3).
  - `select.<name>_navigation_mode`: Select navigation mode (`normal`, `extra_care`, `deep` on Gen3; `normal`, `gentle` on Gen4).

## Installation into Home Assistant (`home`)
To deploy directly to your Home Assistant server on `home`:
```bash
scp -r /home/abewi/hass-vacuula/custom_components/vacuula home:~/docker-images/home-assistant/config/custom_components/
ssh home "sudo docker restart homeassistant"
```
Then in Home Assistant, go to **Settings → Devices & Services → Add Integration → Vacuula** and enter `http://vacuula.lan` (or `http://172.18.0.1:8085`).
