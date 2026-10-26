# Architecture & Technical Design: `hass-vacuula` (`v0.6.2`)

## 1. Overview & Goals
`hass-vacuula` is a zero-dependency Home Assistant custom integration (distributable via **HACS**) that connects a local [Vacuula](https://github.com/vacuula/vacuula) server instance to Home Assistant. Because a single Vacuula server can manage multiple Neato robots across both **Gen3** (`D3`–`D7`, e.g., `BotVacD7Connected`) and **Gen4** (`D800`, `D8`–`D10`) generations, the integration models the **Vacuula Server** as the `ConfigEntry` hub and registers each paired robot as a Home Assistant `DeviceEntry`.

---

## 2. Repository & Directory Structure

```text
hass-vacuula/
├── LICENSE                                # MIT License
├── hacs.json                              # HACS repository metadata
├── README.md                              # Visual showcase, installation & automation guide
├── ARCHITECTURE.md                        # Technical design & Vacuula API specification
├── COMPATIBILITY.md                       # Cross-version compatibility matrix (Vacuula v1.0.0, v1.1.0+)
├── CHANGELOG.md                           # Release notes per version
├── docs/
│   └── assets/
│       ├── card_preview.svg               # High-DPI preview of custom:vacuula-map-card
│       ├── floor_map.png                  # Rendered RLE floorplan with room polygons
│       └── last_run_map.png               # Rendered cleaning coverage & trajectory map
└── custom_components/
    └── vacuula/
        ├── __init__.py                    # ConfigEntry setup, static frontend registration, actions
        ├── manifest.json                  # Integration manifest (zeroconf: _vacuula._tcp.local.)
        ├── const.py                       # Domain constants, enums, and command mappings
        ├── api.py                         # Async HTTP + SSE client with per-robot asyncio.Lock
        ├── coordinator.py                 # Hybrid SSE push + 30s fallback poll DataUpdateCoordinator
        ├── config_flow.py                 # UI setup flow (manual, Zeroconf mDNS, & reconfigure)
        ├── diagnostics.py                 # Redacted config-entry & per-robot device diagnostics
        ├── entity.py                      # Base VacuulaEntity binding entities to robot DeviceInfo
        ├── map_renderer.py                # Pure-Python RLE-to-PNG renderer & polygon coordinate normalizer
        ├── image.py                       # Floor Map & Last Run Map image entities
        ├── vacuum.py                      # StateVacuumEntity (Gen3 & Gen4 adapters + zone metadata)
        ├── sensor.py                      # Battery %, status detail, alert, last clean area/duration, total runs
        ├── binary_sensor.py               # Connected, docked, charging, bin full, dock seen, installer outdated
        ├── button.py                      # Dismiss alert, refresh maps, explore map, dynamic per-room buttons
        ├── switch.py                      # Schedule Enable/Disable toggle
        ├── select.py                      # Navigation Mode & Target Zone / Cleaning Category selectors
        ├── icons.json                     # Material Design icons for custom actions
        ├── services.yaml                  # Custom action schemas (clean_zones, clean_spot, refresh_maps)
        ├── strings.json                   # UI strings
        ├── translations/
        │   └── en.json                    # English localization
        └── frontend/
            └── vacuula-map-card.js        # Bundled Lovelace interactive map & room zone Web Component
```

---

## 3. Vacuula Server API Specification

The Vacuula server exposes a local HTTP JSON + Server-Sent Events (SSE) API (typically port `8085` directly or port `80` via reverse proxy).

### 3.1 Server & Discovery Endpoints
| Method | Endpoint | Description | Sample Response |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/server` | Server version, ports, and timezone | `{"version": "1.0.0", "gen4_port": 3443, "timezone": "Europe/Amsterdam", "utc_offset_minutes": 120}` |
| `GET` | `/api/robots` | Map of all paired robots keyed by serial | `{"OPS01234-001122334455": {"type": "neato.gen3", "connected": true, "name": "Mappa"}}` |
| `GET` | `/api/events` | Server-wide SSE stream (`event: robots` on connect/disconnect/rename) | `event: robots\ndata: {"OPS01234-...": {...}}\n\n` |

### 3.2 Per-Robot Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/robot/{serial}/connect` | Real-time SSE stream of robot state updates & events |
| `POST` | `/api/robot/{serial}/command` | Synchronous command execution (serialized per robot via `asyncio.Lock`) |
| `GET` | `/api/robot/{serial}/maps` | List saved persistent maps (`PersistentMap` for Gen3, `FloorPlan` for Gen4) |
| `GET` | `/api/robot/{serial}/maps/{map_id}` | Fetch RLE floorplan JSON (`floormap.json`) |
| `GET` | `/api/robot/{serial}/maps/{map_id}/boundaries` | Fetch Gen4 zones/no-go polygons (`Gen3` uses `getMapBoundaries` command) |
| `GET` | `/api/robot/{serial}/runs` | List historical cleaning runs |
| `GET` | `/api/robot/{serial}/run/{run_id}` | Fetch RLE cleaning run trajectory & coverage JSON (`runmap.json`) |

---

## 4. Generation-Specific Protocol Normalization (`neato.gen3` vs `neato.gen4`)

Both generations use `POST /api/robot/{serial}/command`, abstracted behind [`VacuulaApiClient`](custom_components/vacuula/api.py):

| Action | Gen3 (`neato.gen3` — D3 to D7) | Gen4 (`neato.gen4` — D800, D8 to D10) |
| :--- | :--- | :--- |
| **Poll State** | `{"cmd": "getRobotState"}` | `{"ability": "state.show"}` |
| **Start House/Map Clean** | `{"cmd": "startCleaning", "params": {"category": 4, "mode": 2, "navigationMode": 1}}` *(category `2`=House, `4`=Map)* | `{"ability": "cleaning.start", "runs": [{"map": {"rank_id": "...", "track_id": null, "nogo_enabled": true}, "settings": {...}}]}` |
| **Start Zone Clean** | `{"cmd": "startCleaning", "params": {"category": 4, "mode": 2, "navigationMode": 1, "boundaryId": "..."}}` (supports string or array of UUIDs) | `{"ability": "cleaning.start", "runs": [{"map": {"rank_id": "...", "track_id": "...", "nogo_enabled": true}, "settings": {...}}]}` |
| **Start Spot Clean** | `{"cmd": "startCleaning", "params": {"category": 3, "mode": 2, "navigationMode": 1, "spotWidth": 200, "spotHeight": 200}}` | *(Unsupported in Gen4 API)* |
| **Pause / Resume / Stop** | `pauseCleaning` / `resumeCleaning` / `stopCleaning` | `cleaning.pause` / `cleaning.resume` / `cleaning.cancel` |
| **Return to Dock** | `{"cmd": "sendToBase"}` | `{"ability": "navigation.return_to_base"}` |
| **Locate Robot** | `{"cmd": "findMe"}` | `{"ability": "utilities.find_me"}` |
| **Dismiss Alert** | `{"cmd": "dismissCurrentAlert"}` | *(Handled automatically)* |
| **Schedule Toggle** | `{"cmd": "enableSchedule"}` / `{"cmd": "disableSchedule"}` | *(Gen3 only)* |

---

## 5. Pure-Python High-DPI Map Renderer & Interactive Coordinate Pipeline

1. **RLE Decoding & Scanline Polygon Rasterization ([`map_renderer.py`](custom_components/vacuula/map_renderer.py))**:
   - Decodes Vacuula's run-length encoded (`rle`) floor grid (`0`=unknown, `1`=free floor, `2`=wall) onto a dark-slate (`#181c24`) RGBA canvas.
   - Input is bounded before allocation: maps larger than `MAX_MAP_DIM` (`4096×4096`) are rejected, and each RLE run is capped at the remaining expected buffer length, so a malformed or hostile `count` can never trigger a multi-gigabyte allocation.
   - Rasterizes named room zone polygons (`type == "polygon"`) using scanline alpha blending (`alpha=0.40`) restricted to free-floor pixels so walls stay crisp.
   - Overlays `runmap.json` coverage (`val == 3` cyan tint, `val == 150` trajectory path) when rendering `image.<robot>_last_run_map`.
   - Draws polygon borders (`thickness=1`), red No-Go lines (`thickness=2`), and the green dock pin *on top* of the coverage layer.
   - Auto-crops to the non-empty bounding box (`pad=16` pixels), applies 2× nearest-neighbor high-DPI upscaling (`_upscale_2x`), and encodes a standards-compliant RGBA PNG using only Python's standard library (`zlib` + `struct`).
2. **Cropped Coordinate Normalization (`compute_cropped_zones`)**:
   - Computes the exact `[0..1]` normalized centroid (`x`, `y`) and polygon vertices (`points`) relative to the **cropped** bounding box and exposes them in the `zones` attribute of `image.<robot>_floor_map` and `image.<robot>_last_run_map`.
   - [`vacuula-map-card.js`](custom_components/vacuula/frontend/vacuula-map-card.js) uses these normalized coordinates to position interactive SVG polygon highlights and clickable room pills directly over the `image.<robot>_floor_map` / `image.<robot>_last_run_map` image with pixel-accurate alignment.
3. **Zero-Flicker Shadow DOM State Diffing**:
   - Because Home Assistant invokes `set hass(hass)` on custom cards whenever *any* entity in the home changes state, `VacuulaMapCard._computeSignature()` computes a lightweight state signature from only the target robot's vacuum, map images, schedule switch, and telemetry sensors—updating the DOM only when the robot's own state or user selection changes.
   - The signature includes the full `zones` attribute and display names, so renaming or recoloring a room on the Vacuula server re-renders the card.
   - `VacuulaMapCardEditor` only rebuilds its form when the set of `vacuum.*` entities changes, and skips re-rendering from `setConfig()` while the title input has focus, so typing is never interrupted by unrelated state updates.

---

## 6. Security & Robustness

Data rendered or requested by the integration originates from the Vacuula server (room names are user-defined) and from service call payloads, so it is treated as untrusted.

| Area | Safeguard |
| :--- | :--- |
| **Lovelace card ([`vacuula-map-card.js`](custom_components/vacuula/frontend/vacuula-map-card.js))** | Every interpolated value is passed through `escapeHtml()` (`&`, `<`, `>`, `"`, `'`) before being assigned to `innerHTML` (card and editor). Zone colors used in inline `style` attributes are validated by `sanitizeColor()` (hex or named colors only, falling back to `#38bdf8`). Map image URLs are restricted by `sanitizeImgUrl()` to relative or `http(s)` URLs, blocking `javascript:`/`data:` URIs. |
| **API client ([`api.py`](custom_components/vacuula/api.py))** | `serial`, `map_id`, and `run_id` are percent-encoded per path segment (`_seg()`), and empty, `.`, and `..` segments are rejected to prevent path traversal on the server. Connection errors, timeouts, and invalid JSON are all wrapped in `VacuulaApiError`. |
| **Error surfacing** | `VacuulaApiError` subclasses `HomeAssistantError`, so failed entity commands and actions show a UI notification instead of an unhandled traceback. |
| **Map renderer ([`map_renderer.py`](custom_components/vacuula/map_renderer.py))** | Map dimensions are bounded by `MAX_MAP_DIM`, and RLE runs are capped (see §5). |
| **Config flow ([`config_flow.py`](custom_components/vacuula/config_flow.py))** | `_normalize_url()` accepts only `http`/`https` URLs with a valid host and port (defaulting to `http://`), rejecting anything else with an `invalid_url` form error rather than a server error. Zeroconf IPv6 hosts are bracketed, and link-local addresses are ignored. Reconfiguring the URL updates the entry's unique ID and aborts if another entry already uses it. |
| **Diagnostics ([`diagnostics.py`](custom_components/vacuula/diagnostics.py))** | Output passes through `async_redact_data()` (serials, MACs, secrets, tokens, URLs, unique IDs). Robots are keyed `robot_1…n` rather than by serial. |
| **Task lifecycle ([`coordinator.py`](custom_components/vacuula/coordinator.py))** | The coordinator receives its `ConfigEntry`, and SSE-triggered refreshes run via `config_entry.async_create_background_task()`, so in-flight work is cancelled when the entry is unloaded. |
