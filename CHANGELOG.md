# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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

[0.5.2]: https://github.com/Snuggert/hass-vacuula/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/Snuggert/hass-vacuula/releases/tag/v0.5.1
