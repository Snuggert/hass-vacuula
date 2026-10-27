# Vacuula Server & Integration Compatibility Matrix

This document details cross-version compatibility between **Neato Botvac for Home Assistant** (`hass-vacuula`), upstream **Vacuula server** releases, Neato robot vacuum generations, and robot installer firmware versions.

---

## Compatibility Matrix

| Integration Version | Home Assistant | Python | Vacuula Server v1.0.0 | Vacuula Server v1.1.0+ | Gen3 Botvac (D3–D7) | Gen4 Botvac (D8–D10) | Gen2 Botvac (OG) | Outdated Installer Alert | Gen4 Flipped Dock Align | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **v0.7.1** | `2026.3.0+` | `3.14+` | ✅ Full | ✅ Full | ✅ Full | ✅ Full | 🚧 Roadmap | ✅ Supported | ✅ Supported | **Current / Recommended** |
| **v0.7.0** | `2026.3.0+` | `3.14+` | ✅ Full | ✅ Full | ✅ Full | ✅ Full | 🚧 Roadmap | ✅ Supported | ✅ Supported | Previous Stable |
| **v0.6.2** | `2025.1.0+` | `3.12+` | ✅ Full | ✅ Full | ✅ Full | ✅ Full | 🚧 Roadmap | ✅ Supported | ✅ Supported | Previous Stable |
| **v0.6.1** | `2025.1.0+` | `3.12+` | ✅ Full | ⚠️ Compatible | ✅ Full | ⚠️ Partial | 🚧 Roadmap | ❌ No | ❌ No | Legacy |
| **v0.6.0** | `2025.1.0+` | `3.12+` | ✅ Full | ⚠️ Compatible | ✅ Full | ⚠️ Partial | 🚧 Roadmap | ❌ No | ❌ No | Legacy |
| **v0.5.2** | `2025.1.0+` | `3.12+` | ✅ Full | ⚠️ Compatible | ✅ Full | ⚠️ Partial | 🚧 Roadmap | ❌ No | ❌ No | Legacy |

> **Definitions:**
> - **Full**: All features verified and supported natively with zero known discrepancies.
> - **Compatible**: Basic cleaning commands and state polling work, but new server features (such as dynamic ports, installer warnings, or revised dock coordinates) are not integrated.
> - **Partial**: Floorplans and runs display, but dock markers may exhibit Y-axis coordinate offset on Gen4 floorplans.
> - **Roadmap**: Upstream Vacuula server does not yet support this generation (support is currently under active development upstream).

---

## Vacuula Server Releases

### Vacuula Server v1.1.0+ (Latest Upstream Release)

*Released October 2026*

| Change in Vacuula v1.1.0 | Upstream Description | Integration v0.7.0 Handling |
| :--- | :--- | :--- |
| **Default Port `8050`** | Default `VACUULA_PORT` moved from `80` to `8050` to prevent collisions with host dashboards. | **Native Support**.<br>`DEFAULT_URL` updated to `http://vacuula.local:8050`. Zeroconf auto-discovers port 8050 or any custom port automatically. |
| **Gen3 Dedicated Port `335`** | Robot TLS communication moved from port 443 to customizable `GEN3_PORT` (default 335). | **Decoupled**.<br>The integration communicates strictly with `VACUULA_PORT` via HTTP/SSE. Gen3 TLS robot socket port does not affect HA. |
| **Server Metadata API** | `GET /api/server` provides `min_installer_version`, `gen3_port`, `gen4_port`, and `ha_ingress`. | **Cached & Exposed**.<br>Coordinator caches metadata for runtime validation and diagnostics export. |
| **Installer Version Tracking** | Robot snapshot reports `installed_with` (e.g. `"1.0.0"` or `"1.1.0-b6"`). | **Tracked & Alerted**.<br>Exposed via `binary_sensor.<robot>_installer_outdated` (`problem` class) and attributes on `vacuum.<robot>`. |
| **Gen4 Dock Y-Coordinate Flip** | Commit `ce2f53c` inverted Gen4 base coordinates (`y = 1 - norm_y`) to align with canvas space. | **Aligned**.<br>Pure-Python `map_renderer.py` accounts for the inverted Y dock position in world coordinate metadata. |
| **Persistent Map Promotion** | `beehive.py` promotes persistent maps when subsequent uploads are valid. | **Handled**.<br>Coordinator map refresh automatically picks up promoted floorplans and boundaries. |
| **Schedule Timezone Resolution** | Robot stores schedules in local time directly rather than requiring web UI UTC offsets. | **Compliant**.<br>Integration schedule toggle commands (`enableSchedule`/`disableSchedule`) operate cleanly without altering timetable data. |
| **Home Assistant Ingress** | Vacuula add-on supports Ingress for iframe embedding (`/api/hassio_ingress/...`). | **Compliant**.<br>Integration connects via standard host network port (`8050`), avoiding supervisor token/session restrictions. |

---

### Vacuula Server v1.0.0 (Initial Upstream Release)

*Released October 2026*

* **Compatibility Status**: **Fully Supported (Backward-Compatible)** in `v0.7.0`.
* **Behavior in v0.7.0**:
  * Default port 80 and custom ports (e.g. `8085`) are supported.
  * When `min_installer_version` or `installed_with` is not returned by the server, the integration gracefully falls back and keeps `binary_sensor.<robot>_installer_outdated` in an inactive state (`off`).
  * Dock rendering on Gen3 continues to draw from floormap pixel metadata.

---

## Robot Generation & Installer Firmware Compatibility

### Gen3: Neato Botvac Connected (D3, D4, D5, D6, D7)

All Gen3 models are fully supported by `hass-vacuula`.

#### Robot Installer Versions

When you flash your Gen3 robot to connect to Vacuula, the installer tool version is recorded in the Vacuula database:

| Installer Version | Vacuula Server v1.0.0 | Vacuula Server v1.1.0+ | Integration `binary_sensor.<robot>_installer_outdated` | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **`< 1.1.0-b3`** (e.g. `1.0.0`) | ✅ Compatible | ⚠️ Functional (Update Suggested) | **ON** (`problem`) | Uses legacy port 443 comms. Vacuula v1.1.0 recommends re-flashing to support dynamic Gen3 ports (`335`). |
| **`>= 1.1.0-b3`** (e.g. `1.1.0-b6`, `1.1.0`) | ✅ Compatible | ✅ Optimal | **OFF** (`normal`) | Full support for dynamic `GEN3_PORT` and local schedule time storage. |
| **`dev` versions** | ✅ Compatible | ✅ Optimal | **OFF** (`normal`) | Development builds are exempted from outdated version warnings. |

---

### Gen4: Neato Botvac (D8, D9, D10)

All Gen4 models are fully supported by `hass-vacuula`.

* **Connection**: Gen4 robots communicate over TCP/TLS on port `3443`.
* **Map Alignment**:
  * In `v0.6.2+`, `map_renderer.py` automatically checks for `metadata` (`resolution`, `origin_x`, `origin_y`) and applies the v1.1.0 inverted Y dock position (`height - 1 - py`), ensuring dock icons match the rendered walls.
* **Installer Version**: Gen4 robots do not use the Gen3 installer versioning schema; `installed_with` remains `None` and the outdated installer binary sensor is omitted for Gen4 devices.

---

### Gen2: Neato Botvac Connected (Original) & Gen1

* **Gen2 (BotVac Connected Original)**: Upstream Vacuula has Gen2 support on its development roadmap, but it is not yet available in server releases. Once upstream publishes Gen2 support, `hass-vacuula` will add support.
* **Gen1 (Non-Connected)**: Gen1 Neato robots lack Wi-Fi hardware and cannot communicate with Vacuula or Home Assistant.

---

## Network Ports & Topology Reference

The integration and Vacuula communicate over your local area network (LAN):

```
+-----------------------------------+
|      Neato Robot Vacuum           |
|   (D3-D7 Gen3 / D8-D10 Gen4)      |
+-----------------+-----------------+
                  |
                  | Robot TLS Comms
                  | Gen3: Port 335 (v1.1) / 443 (v1.0)
                  | Gen4: Port 3443
                  v
+-----------------+-----------------+
|         Vacuula Server            |
|   (Docker / Add-on / TrueNAS)     |
|   Database: vacuula.db            |
+-----------------+-----------------+
                  |
                  | REST API & SSE Push
                  | Port 8050 (v1.1 default) / Port 80 (v1.0 default)
                  v
+-----------------+-----------------+
|         Home Assistant            |
|   Integration: hass-vacuula       |
|   Card: custom:vacuula-map-card   |
+-----------------------------------+
```

| Port | Config Key | Protocol | Usage | Used by Integration? |
| :--- | :--- | :--- | :--- | :---: |
| **8050** *(or 80)* | `VACUULA_PORT` | HTTP | Server Web UI, REST API, SSE event streams | **Yes** (Primary interface) |
| **335** *(or 443)* | `GEN3_PORT` | TLS | Gen3 robot hardware socket | No (Internal to Vacuula server) |
| **3443** | `GEN4_PORT` | TCP/TLS | Gen4 robot hardware socket | No (Internal to Vacuula server) |

---

## Frequently Asked Compatibility Questions

### What does the `Installer Outdated` problem sensor mean?
If `binary_sensor.<robot>_installer_outdated` turns **ON**, your Gen3 robot was set up with a Vacuula installer older than `1.1.0-b3` (for example, version `1.0.0`). While the robot may continue to clean, upstream Vacuula introduced improvements in `v1.1.0` (such as configurable robot socket ports and refined schedule handling) that require updating the robot using the latest [Vacuula Installer](https://github.com/vacuula/installer).

### I changed my Vacuula server port (e.g. from 80 to 8050). How do I update Home Assistant?
You do not need to delete and re-add your integration!
1. Go to **Settings → Devices & Services → Neato Botvac (Vacuula Client - Unofficial)**.
2. Click the three dots (**⋮**) → **Reconfigure**.
3. Enter the new URL (e.g. `http://vacuula.local:8050`) and submit. All existing entity IDs and dashboard cards are preserved.

### Can I run Vacuula Server v1.0.0 with hass-vacuula v0.7.0?
**Yes.** `hass-vacuula` v0.7.0 maintains backwards compatibility with Vacuula server v1.0.0. Missing metadata fields from v1.0.0 are automatically defaulted without throwing errors.
