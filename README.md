# Vacuula Home Assistant Integration (`hass-vacuula`)

Custom [Home Assistant](https://www.home-assistant.io/) integration (HACS-compatible) for [Vacuula](https://github.com/vacuula/vacuula) — the local replacement cloud server for Neato Botvac Connected (Gen3: D3–D7, Gen4: D800/D8–D10) robot vacuums.

See [ARCHITECTURE.md](file:///home/abewi/hass-vacuula/ARCHITECTURE.md) for the full design outline, API specification, and Gen3/Gen4 protocol mapping.

## Features
- **Auto-Discovery**: Automatically discovers your Vacuula server on the LAN via mDNS (`_vacuula._tcp.local.`) or connects via URL (e.g., `http://vacuula.lan`).
- **Multi-Robot & Multi-Generation**: Supports both **Gen3** (`D3`, `D4`, `D5`, `D6`, `D7`) and **Gen4** (`D800`, `D8`, `D9`, `D10`) Neato robots managed by a single Vacuula server.
- **Full Vacuum Controls**: Start, Pause, Resume, Stop, Return to Base, Locate (`findMe`), and Fan Speed (`Eco` / `Turbo`).

## Installation into Home Assistant (`home`)
To deploy directly to your Home Assistant server on `home`:
```bash
scp -r /home/abewi/hass-vacuula/custom_components/vacuula home:~/docker-images/home-assistant/config/custom_components/
ssh home "sudo docker restart homeassistant"
```
Then in Home Assistant, go to **Settings → Devices & Services → Add Integration → Vacuula** and enter `http://vacuula.lan` (or `http://172.18.0.1:8085`).
