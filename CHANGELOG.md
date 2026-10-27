# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.8.0] - 2026-10-27

> **Special Thanks:** A huge thank you to **@veronoicc** ([#3](https://github.com/Snuggert/hass-vacuula/pull/3)) for this contribution! This release introduces Hass native room/segment cleaning, new custom actions, server hub diagnostic entities, dynamic options flow, and frontend card polish.

### Added
- **New Custom Actions / Services (`custom_components/vacuula/`):**
  - `vacuula.clean_zone`: Start cleaning a single persistent map zone or room by name with optional `map_name`, `mode`/`fan_speed`, and `navigation_mode`.
  - `vacuula.dismiss_alert`: Clear the active alert/notification on a Gen3 robot.
  - `vacuula.send_raw_command`: Dispatch raw Gen3 commands (`cmd`) or Gen4 abilities (`ability`) directly to a robot with optional parameters dictionary.
  - Added `async_send_raw_command` to `VacuulaApiClient` (`core/client.py`).
  - Added action schemas, selector definitions, and translations in `services.yaml`, `icons.json`, `strings.json`, and `translations/en.json`.
- **Modern Segment & Spot Cleaning on Vacuum Entity (`custom_components/vacuula/vacuum.py`):**
  - Implemented `async_clean_spot` for Gen3 localized spot cleaning.
  - Implemented Home Assistant's modern area cleaning contract via `Segment` dataclass, `async_get_segments()`, and `async_clean_segments()`.
  - Dynamically flags `VacuumEntityFeature.CLEAN_SPOT` and `FEATURE_CLEAN_AREA`.
- **Clean Selected Zone Button (`custom_components/vacuula/button.py`):**
  - Added `VacuulaCleanSelectedZoneButton` (`button.<robot>_clean_selected_zone`) to clean whichever zone is currently selected by `select.<robot>_target_zone` (or full house if set to `all`).
- **Server Hub Device & Diagnostic Entities (`custom_components/vacuula/`):**
  - Registered Vacuula Server hub device in Device Registry with `DeviceEntryType.SERVICE`, parenting robot vacuums via `via_device`.
  - Added `binary_sensor.server_<id>_status` (`BinarySensorDeviceClass.CONNECTIVITY`).
  - Added `sensor.server_<id>_version` (`EntityCategory.DIAGNOSTIC`).
  - Added `sensor.server_<id>_connected_robots` (measurement sensor tracking count of connected robots).
  - Extracted shared `VacuulaServerEntity` base class in `entity.py` to keep server hub platform definitions concise and DRY.
- **Config Entry Options Flow (`custom_components/vacuula/config_flow.py`):**
  - Added `VacuulaOptionsFlowHandler` to configure polling `scan_interval` (5–300s slider) via Home Assistant UI.
  - Added reload listener in `__init__.py` and dynamic update interval handling in `VacuulaCoordinator`.
- **Lovelace Map Card Polish (`custom_components/vacuula/frontend/vacuula-map-card.js`):**
  - Added SVG alert icons and dustbin indicators in alert banners.
  - Added dynamic button label support (`Start`, `Pause`, `Resume`) reflecting robot activity state.
  - Updated card preview visual asset in `docs/assets/card_preview.svg`.

## [0.7.2] - 2026-10-26

### Changed
- **Dedicated HACS Release Package (`vacuula.zip`) & Archive Filtering (`.gitattributes`):** Configured `zip_release: true` (`filename: "vacuula.zip"`) in `hacs.json` and updated `.github/workflows/release.yml` to build and attach a self-contained `vacuula.zip` containing only `custom_components/vacuula/`. Added `.gitattributes` (`export-ignore`) so GitHub's generated source archives also exclude development tooling, tests, and CI configuration.
- **Unified `devtools` Package & Static Sandbox Assets:** Consolidated `packages/aiovacuula`, `tests/dev_server/`, and `scripts/` into a top-level `devtools/` package (`python -m devtools`) and extracted the developer sandbox UI into static HTML/CSS/JS assets (`devtools/static/`).

## [0.7.1] - 2026-10-26

### Changed
- **O(runs) RLE Span Map Renderer (`custom_components/vacuula/core/map_renderer.py`):** Optimized `get_crop_box()` and `render_map_png()` to walk RLE spans directly instead of per-pixel loops, initialize RGBA buffers at C speed (`bytearray(b"\x18\x1c\x24\xff" * total)`), paint floor/wall/path/dock runs with slice assignment, and encode PNGs with fast `zlib.compress(..., level=1)`.
- **Cached Cropped Zones & Content-Aware Map Cache Key (`custom_components/vacuula/image.py` & `core/models.py`):** Cached `cropped_zones` on `VacuulaRobotData` so `VacuulaFloorMapImage` and `VacuulaLastRunMapImage` state updates read normalized zones in $O(1)$ without main-thread RLE decoding, and keyed PNG image caching on `boundary_signature` so room renames and color changes invalidate cached map images immediately.
- **Concurrent Map Detail, Boundary & Run Detail Fetching (`custom_components/vacuula/core/controller.py`):** Parallelized `async_get_map_detail`, `async_get_map_boundaries`, and `async_get_run_detail` in `async_load_robot_maps_and_runs()` via `asyncio.gather(..., return_exceptions=True)`, and parallelized multi-robot `vacuula.refresh_maps` calls.
- **Core / Coordinator Deduplication & Entity Conciseness:** Unified robot polling, map/run loading, and Gen3 command-response application across `VacuulaController` and `VacuulaCoordinator`, delegated Gen3/Gen4 entity state properties to `VacuulaRobotData`, and added `PARALLEL_UPDATES = 0` across all 7 entity platforms.

### Fixed
- **Gen4 `is_docked` and `is_charging` Normalization:** Unified `VacuulaRobotData.is_docked`, `is_charging`, and `activity_state` to inspect both top-level `body` and `body["details"]` on Gen4 `FullRobotState` payloads.

## [0.7.0] - 2026-10-26

### Added
- **Zero-HA Decoupled Core (`custom_components/vacuula/core/` & `packages/aiovacuula`):** Extracted the Vacuula protocol constants, async REST + SSE client (`VacuulaApiClient`), pure-Python RLE PNG map renderer (`render_map_png`), and domain state controller (`VacuulaController`) into a self-contained core subpackage with **zero Home Assistant dependencies**, exposed as the `aiovacuula` uv workspace package while keeping `"requirements": []` in `manifest.json` for 100% HACS compatibility.
- **Full-Stack Developer Workbench & Sandbox (`scripts/run_vacuula_dev_server.py` & `tests/dev_server/`):** Single-command developer environment that spins up a real upstream `vacuula_server` (`:8050`), simulated Neato Botvac D7 robot(s) (`MockNeatoRobot`) with seeded RLE floorplans and run history, the actual `custom_components/vacuula` integration in-process (all 25 entities across all 7 Home Assistant platforms), and a 3-column browser workbench (`:8124`) featuring `<vacuula-map-card>`, `<vacuula-map-card-editor>`, the live Integration Entity & Device Registry Inspector, and the **Developer Event & Scenario Studio**.
- **Developer Event & Scenario Studio:** Added 1-click triggers in the browser sandbox and interactive CLI for cleaning lifecycle transitions (`clean`, `house_clean`, `spot`, `explore`, `pause`, `stop`, `dock`, `finish_run`), all hardware alerts (`dustbin_full`, `dustbin_missing`, `maint_brush_change`, `maint_filter_change`, `clear_path`, `nav_floorplan_not_created`), hardware errors (`ui_error_brush_stuck`, `ui_error_Brush_overload`, `ui_error_navigation_stuck`, `ui_error_bumper_stuck`, `ui_error_picked_up`, `ui_error_undock_failed`), live battery slider, installer version switching (`1.0.0-b28` vs `1.1.0-b3`), and Wi-Fi drop/reconnect simulation.
- **Decoupled Core & Live Server Test Suites:** Added `tests/core/test_core_decoupled.py` (verifying `sys.modules` has zero `homeassistant` imports) and `tests/test_live_vacuula_server.py` (testing end-to-end against a real `vacuula_server` process and browser sandbox).

### Changed
- **Migrated to Python 3.14 & Home Assistant 2026.3+:** Upgraded project runtime, type targets, `hacs.json` minimum Home Assistant version (`2026.3.0`), `requirements_test.txt` floor bounds, `uv.lock`, and GitHub Actions validation workflows to Python 3.14, matching the upstream `vacuula_server` runtime and removing legacy pre-2026 compatibility shims.

### Fixed
- **Per-Robot Command Lock Eviction:** Evicted disconnected robot `asyncio.Lock` instances in `VacuulaApiClient.evict_stale_locks()` to prevent unbounded lock dictionary growth over long runtimes.
- **Explicit Authentication Error Classification:** `VacuulaApiClient._request()` now raises `VacuulaAuthError` on HTTP 401/403 responses.
- **Robust Hostname Extraction in Config Flow:** Replaced fragile string splitting in `config_flow.py` title generation with `urllib.parse.urlparse(url).hostname`.
- **Gen3 SSE Frame Validation:** `VacuulaCoordinator._listen_robot_events` now verifies `"state" in frame["data"]` before overwriting robot state, ignoring non-state keepalive frames (`ping`).
- **Mock Neato Persistent Socket Stability:** Replaced `sock.makefile()` with a non-corrupting `select.select()` + `bytearray` chunked stream reader with 15-second keepalive `ping` frames so idle simulated robots never time out against `vacuula_server`.

## [0.6.2] - 2026-10-26

### Added
- **Full Vacuula v1.1.0 Release Compliance:** Added comprehensive support and cross-version compatibility for the upstream Vacuula server v1.1.0 release.
- **Outdated Robot Installer Detection:** Added `binary_sensor.<robot>_installer_outdated` (`VacuulaOutdatedInstallerBinarySensor`) with device class `problem` and category `diagnostic` to notify users when a Gen3 robot was flashed with an older installer version (< `1.1.0-b3`) that requires updating for full v1.1 compatibility.
- **Diagnostic Attributes for Installer Versions:** Added `installed_with` and `outdated_installer` state attributes to `vacuum.<robot>`, as well as inclusion in downloadable device diagnostics.
- **Server Metadata Caching:** Coordinator now caches extended Vacuula server metadata (`min_installer_version`, `gen3_port`, `gen4_port`, `ha_ingress`, `timezone`) for diagnostic inspections.
- **Gen4 Map Dock Coordinate Alignment:** Enhanced pure-Python `map_renderer.py` to handle inverted Gen4 Y-dock coordinates introduced in Vacuula v1.1.0 alongside world coordinate fallbacks.
- **Vacuula Prerequisite Callout & Architecture Diagram:** Added clear prerequisite documentation and a Mermaid system architecture diagram to `README.md` clarifying that an existing Vacuula server is required on the local network.
- **Cross-Version Compatibility Matrix:** Added dedicated `COMPATIBILITY.md` detailing interoperability across Vacuula server releases (v1.0.0, v1.1.0+), Neato robot generations (Gen3, Gen4), and installer firmware versions.

### Changed
- **Default Server Port Updated:** Updated `DEFAULT_URL` in `const.py` to `http://vacuula.local:8050` reflecting the upstream Vacuula v1.1.0 default port change from 80 to 8050 and official mDNS hostname `vacuula.local`. Dynamic Zeroconf discovery continues to support any custom port.

## [0.6.1] - 2026-10-25

### Changed
- **Renamed Integration for HACS Clarity:** Renamed display name in `manifest.json` and `hacs.json` to **"Neato Botvac (Vacuula Client - Unofficial)"** to make it abundantly clear this is an independent community client, preventing user confusion with the upstream Vacuula server project.
- **Original MDI-Style Brand Assets:** Replaced all brand assets (`icon.png`, `dark_icon.png`, `logo.png`, `dark_logo.png`, and `@2x` variants) with original Home Assistant Material Design style artwork depicting a Neato D-shape robot vacuum in HA blue/cyan and dark mode silver. Removed all upstream Vacuula artwork and trademarks.
- **Upstream Separation & Support Boundaries:** Added prominent disclaimers in `README.md` and documentation explicitly stating this project is independent, not affiliated with or endorsed by the upstream Vacuula project, and directing all support questions and issues exclusively to the `hass-vacuula` GitHub repository.

## [0.6.0] - 2026-10-25

### Added
- **Responsive Multi-Device Map Sizing:** `vacuula-map-card` now scales dynamically across device form factors. Mobile screens (< 600px) preserve their compact 380px cap, while tablet (520px max), desktop (660px max), and 4K/ultrawide displays (800px max) expand to showcase high-DPI floorplans and cleaning coverage.
- **Lovelace Sections & Panel Views:** Native support for Home Assistant 2024+ Sections grid layout via `getGridOptions()`, as well as full-height scaling in Lovelace panel views.
- **Dust Bin Full Problem Sensor:** Added `binary_sensor.<robot>_bin_full` (`VacuulaBinFullBinarySensor`) with device class `problem` and icon `mdi:delete-empty` to alert when the robot's dust bin requires emptying or is unseated.
- **Interactive Alert & Error Notification Banners:** Prominent notification banner on the card rendering color-coded alerts (amber warnings for `dustbin_full`, `clear_path`, `lid_open`; red errors for `brush_stuck`, `navigation_stuck`, `cliff_sensor`) with friendly human text and a one-tap `✕ Dismiss` button.
- **Header Dust Bin Badge:** Subtle `🗑️ Bin Full` pill in the header telemetry bar when dust bin attention is required.
- **Granular Card Configuration Toggles:** Added individual boolean controls in YAML and the visual card editor for `map_height` (Auto, Compact, Medium, Large, Extra Large), `expand_on_desktop`, `show_header`, `show_status_badge`, `show_battery`, `show_schedule`, `show_alerts`, `show_bin_alert`, `show_toolbar`, `show_zone_labels`, `show_zone_chips`, `show_controls`, and `show_modes`.
- **Card Editor Redesign:** Organized `VacuulaMapCardEditor` into clean categorized sections with switch controls.
- **Full Brand Asset Suite & Dark Mode Support:** Added all 8 specification-compliant Home Assistant and HACS brand assets (`icon.png`, `icon@2x.png`, `dark_icon.png`, `dark_icon@2x.png`, `logo.png`, `logo@2x.png`, `dark_logo.png`, `dark_logo@2x.png`). Dark theme variants provide high-contrast silver/white artwork with vivid red status accents for clear visibility in dark mode.
- **Brand Generation Tooling & Test Suite:** Added `scripts/generate_brands.py` and dedicated unit tests in `tests/test_brand.py` verifying file completeness, resolutions (256×256 and 512×512), RGBA formatting, and light/dark theme contrast.
- **Development Tooling:** Added git pre-commit and pre-push hooks running linter and unit tests automatically before commits and pushes.

### Fixed
- **HACS & Marketplace Dark Icon Resolution:** Resolved missing `dark_icon.png` in HACS community store (`https://brands.home-assistant.io/_/vacuula/dark_icon.png`) and Home Assistant Marketplace by bundling complete local brand assets and upgrading `icon.png` to standard 256×256 px.

## [0.5.2] - 2026-10-24

### Added
- **Vacuula Target Platform:** Targeted and validated against official Vacuula server release **v1.0.0** (with forward-compatibility verified against upcoming v1.1.0-dev builds). Going forward, `hass-vacuula` intends to closely follow the official Vacuula release schedule, keeping feature parity, protocol schemas, and API compatibility synchronized as new Vacuula versions are published.
- **Quality & Testing Suite:** Comprehensive automated test suite with pytest covering config flow, API client, map renderer, diagnostics, coordinator, domain services, and vacuum platform.
- **Continuous Integration:** Hardened GitHub Actions CI pipeline running Hassfest, HACS validation (9/9 checks), Ruff linting & formatting, Mypy static type checking, and Pytest across Python 3.12 and 3.13 matrix.
- **Gated Releases:** Release pipeline automatically gated on passing quality validations before publishing GitHub Releases.

### Security
- **Lovelace card:** every value interpolated into `innerHTML` is now HTML-escaped (`&`, `<`, `>`, `"`, `'`) in both the card and the visual editor. This covers entity IDs, titles and friendly names, states, subtitles, zone names, the start button label, fan speeds, navigation modes and battery values. Room names containing markup are no longer rendered as HTML.
- **Lovelace card:** zone colors are validated before use in inline styles, and map image URLs are restricted to relative or `http(s)` URLs.
- **API client:** `serial`, `map_id` and `run_id` are percent-encoded as URL path segments, and `.`/`..` segments are rejected.
- **Map renderer:** RLE run lengths are capped and maps larger than 4096×4096 are rejected, preventing memory exhaustion from malformed map data.
- **Diagnostics:** serials, MAC addresses, secrets, tokens and the server URL are redacted via `async_redact_data`, and robots are no longer keyed by serial.

### Fixed
- The card editor no longer loses focus or cursor position in the title field when other entities update.
- The card now re-renders when a room is renamed or recolored on the Vacuula server.
- Failed commands and actions now show a Home Assistant UI error instead of a traceback (`VacuulaApiError` now subclasses `HomeAssistantError`). Request timeouts and invalid JSON responses are also handled.
- Config flow: URLs without a scheme default to `http://`, and invalid URLs show an `invalid_url` error instead of failing the flow.
- Zeroconf: IPv6 hosts are bracketed correctly, and link-local addresses are ignored.
- Reconfigure: changing the server URL now updates the entry's unique ID and aborts if another entry already uses that URL.
- Background refreshes triggered by server events are now cancelled when the integration is unloaded.

## [0.5.1] - 2026-10-19

### Added
- `icons.json` with icons for custom actions.
- Bundled Vacuula brand icons.
- Hassfest and HACS validation workflow, plus an automated GitHub Release workflow.
- MIT license, plus license and attribution notes in the README.

## [0.5.0]

### Added
- Visual showcase in the README, frontend state diffing in the card, 2× high-DPI map rendering, entity categories and diagnostics.

[0.8.0]: https://github.com/Snuggert/hass-vacuula/compare/v0.7.2...v0.8.0
[0.7.2]: https://github.com/Snuggert/hass-vacuula/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/Snuggert/hass-vacuula/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/Snuggert/hass-vacuula/compare/v0.6.2...v0.7.0
[0.6.2]: https://github.com/Snuggert/hass-vacuula/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/Snuggert/hass-vacuula/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/Snuggert/hass-vacuula/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/Snuggert/hass-vacuula/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/Snuggert/hass-vacuula/releases/tag/v0.5.1
