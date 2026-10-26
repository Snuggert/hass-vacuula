# Vacuula Developer Testing Environment

This guide explains how to set up and use the **Vacuula Developer Testing Environment**, an end-to-end testing and development harness for `hass-vacuula`.

Rather than mocking HTTP endpoints with static fixtures, this environment runs an **actual Vacuula server instance** backed by a **high-fidelity Neato Botvac protocol simulator**. The Home Assistant integration interacts with a real, running Vacuula server, which in turn manages and communicates with simulated Neato robots over persistent chunked HTTP sockets.

---

## Architecture Overview

```mermaid
flowchart LR
    subgraph HomeAssistant ["Home Assistant Core"]
        Integration["custom_components/vacuula<br/>(VacuulaApiClient & Coordinator)"]
        Card["vacuula-map-card<br/>(Lovelace Dashboard)"]
    end

    subgraph DevServer ["Vacuula Dev Server (Actual Codebase)"]
        Router["RouterHandler<br/>(/api/... & /vendors/neato/login)"]
        Database[("SQLite Sandbox DB<br/>(Alembic Migrations)")]
        SSE["SSE Event Bus<br/>(GET /api/events)"]
    end

    subgraph MockRobots ["Mock Neato Robot Device(s)"]
        Robot1["Mock Neato D7<br/>(Gen3 Chunked Protocol)"]
        Robot2["Mock Neato D5<br/>(Legacy Installer v1.0.0)"]
    end

    Integration -->|"REST API (/api/robots, /command)"| Router
    Integration <--|"Real-time SSE Stream"| SSE
    Card --> Integration
    Router <-->|"Chunked HTTP Nucleo & Beehive"| Robot1
    Router <-->|"Chunked HTTP Nucleo & Beehive"| Robot2
    Router --> Database
```

### Key Principles
1. **Authentic Server Logic**: Uses the real upstream Vacuula server codebase (`vacuula_server`) with SQLite database migrations (`alembic upgrade head`), dynamic routing, and SSE event dispatch.
2. **Hardware Simulator**: `MockNeatoRobot` simulates a physical Neato Botvac (Gen3 protocol). It pairs via `POST /links`, establishes the persistent command channel on `POST /vendors/neato/login`, parses incoming command chunks, updates its internal state machine, and replies with standard Neato payloads.
3. **Complete Isolation**: Every test run or dev session operates inside an ephemeral temporary sandbox with its own SQLite database, log file, and TLS certificate—ensuring zero side effects on production or local files.
4. **Zero-Configuration Discovery**: Automatically detects local Vacuula repositories (sibling directory `../vacuula`, `VACUULA_REPO_PATH`, or local `.dev_env/vacuula`) and can automatically clone upstream Vacuula into `~/.cache/hass-vacuula/vacuula` if not present.
5. **Cross-Version Targeting**: Easily test compatibility against Vacuula v1.1.0, v1.0.0, or specific git release tags.

---

## Prerequisites

1. **Python 3.12+** (Python 3.12, 3.13, or 3.14).
2. **uv**: Modern, fast Python package and project manager.
   ```bash
   # Install uv if not already installed
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # Or via pip
   pip install uv
   ```
3. **Git**: Used for repository resolution and version targeting.
4. **OpenSSL**: Used by Vacuula server to generate self-signed dev certificates.

---

## Quickstart: Running the Dev Server

Start the developer server with a single command:

```bash
uv run python scripts/run_vacuula_dev_server.py
```

Output:
```text
Starting Vacuula Dev Server on http://127.0.0.1:8050...
======================================================================
  VACUULA DEVELOPER SERVER (Release: 1.1.0-b9)
  URL:         http://127.0.0.1:8050
  Database:    /tmp/vacuula_dev_.../data/vacuula.db
  Min Install: 1.1.0-b3
  Robots:      1 connected
   - OPS00001-001122334401: 'Living Room Bot' (Model: BotVacD7Connected, Batt: 95%, State: 1, Installer: 1.1.0-b3)
======================================================================
  To test with Home Assistant:
  1. Configure Vacuula integration to point to: http://127.0.0.1:8050
  2. Discovered robots will appear automatically in HA!
======================================================================
Type 'help' for available commands, or 'quit' to exit.
vacuula-dev>
```

---

## Interactive Mock Robot Control

The interactive CLI allows you to trigger live robot actions, simulate state changes, drain batteries, and emit errors while viewing the results in Home Assistant:

| Command | Description | Example |
|---|---|---|
| `status` | Display Vacuula server snapshot and mock robot statuses | `status` |
| `clean [serial]` | Start cleaning cycle (`state=2`, `action=1`) | `clean` |
| `pause [serial]` | Pause cleaning (`state=3`) | `pause` |
| `resume [serial]` | Resume cleaning from pause (`state=2`) | `resume` |
| `stop [serial]` | Stop cleaning and return to idle (`state=1`) | `stop` |
| `dock [serial]` | Send robot to dock (`is_docked=True`, `action=4`) | `dock` |
| `battery [serial] <pct>` | Set battery percentage (0–100) | `battery 45` |
| `alert [serial] <code>` | Trigger an alert code | `alert dustbin_full` |
| `error [serial] <code>` | Trigger an error state | `error ui_error_brush_stuck` |
| `clear [serial]` | Clear active alerts and errors | `clear` |
| `disconnect [serial]` | Simulate robot dropping off WiFi / server | `disconnect` |
| `reconnect [serial]` | Reconnect robot command channel | `reconnect` |
| `add <name>` | Spawn and link a new mock Neato robot | `add Upstairs D7` |
| `help` | Show command reference | `help` |
| `quit` / `exit` | Gracefully shut down server and exit | `quit` |

---

## Running Automated Live Integration Tests

Run the full end-to-end integration test suite against the live Vacuula dev server:

```bash
# Run only the live Vacuula server integration tests
pytest tests/test_live_vacuula_server.py

# Run all tests (unit tests + live dev server tests)
pytest tests/
```

### What the Live Test Suite Verifies
- **Server Health & Metadata**: Confirms `GET /api/server` responds with correct version, minimum installer version, timezone, and port mapping.
- **Robot Discovery & Pairing**: Simulates `POST /links` and verifies appearance in `GET /api/robots`.
- **Command Roundtrips**: Verifies `getRobotState`, `startCleaning`, `pauseCleaning`, `resumeCleaning`, `stopCleaning`, `sendToBase`, `findMe`, `set_schedule_enabled`, and `start_zone_cleaning`.
- **Real-Time SSE Streaming**: Subscribes to `GET /api/events` and verifies push delivery when robots change state or disconnect.
- **Coordinator Synchronization**: Confirms `VacuulaCoordinator` populates entities, updates battery/cleaning status, and detects robot disconnects.
- **Installer Version Compatibility Matrix**: Verifies that robots with legacy installers (`1.0.0-b28`) trigger compatibility flags when server requires `1.1.0-b3`.
- **Multi-Release Compatibility**: Tests integration behavior against historical Vacuula v1.0.0 server configurations.

---

## CLI Options & Customization

The runner script supports several command-line flags for advanced developer workflows:

```bash
python scripts/run_vacuula_dev_server.py [OPTIONS]
```

### Options Reference

| Flag | Default | Description |
|---|---|---|
| `--port PORT` | `8050` | Port for the Vacuula dev server HTTP API |
| `--host HOST` | `127.0.0.1` | Network host interface to bind |
| `--version VERSION` | `1.1.0-b9` | Vacuula server release version to report |
| `--min-installer VER` | `1.1.0-b3` | Minimum installer version required (use `none` for legacy releases) |
| `--robots COUNT` | `1` | Number of initial mock robots to spawn and connect |
| `--robot-installer VER` | `1.1.0-b3` | Installer version sent by mock robots during pairing |
| `--repo PATH` | *(auto-detected)* | Path to Vacuula server repository |
| `--data-dir PATH` | *(ephemeral tmp)* | Path for persistent database and map data |
| `--non-interactive` | `false` | Run continuously without REPL prompt (ideal for daemon/background test setups) |
| `--debug` | `false` | Enable verbose debug logging output |

---

## Testing Against Different Vacuula Releases

You can target different Vacuula releases and version scenarios easily:

### 1. Test Vacuula v1.1.0 (Current Stable Release)
```bash
python scripts/run_vacuula_dev_server.py --version 1.1.0-b9 --min-installer 1.1.0-b3
```

### 2. Test Outdated Neato Robot Installer (Compatibility Warning)
```bash
python scripts/run_vacuula_dev_server.py --version 1.1.0-b9 --min-installer 1.1.0-b3 --robot-installer 1.0.0-b28
```
Discovered robot will report `installed_with: 1.0.0-b28` and `VacuulaCoordinator` will flag the installer as outdated, logging an upgrade recommendation.

### 3. Test Vacuula v1.0.0 (Legacy Release)
```bash
python scripts/run_vacuula_dev_server.py --version 1.0.0 --min-installer none --robot-installer 1.0.0-b28
```

---

## Connecting a Local Home Assistant Instance

To develop and test your Home Assistant instance against the dev server:

1. **Start the Dev Server in Non-Interactive Mode**:
   ```bash
   python scripts/run_vacuula_dev_server.py --port 8050 --non-interactive
   ```
2. **Start Home Assistant Core**:
   ```bash
   hass -c config/
   ```
3. **Add the Vacuula Integration**:
   - In Home Assistant, navigate to **Settings** > **Devices & Services** > **Add Integration**.
   - Search for **Vacuula**.
   - Enter Server URL: `http://127.0.0.1:8050`.
   - Complete the setup—your mock Neato vacuum entity (`vacuum.living_room_bot`) will appear immediately!
4. **Interact with the Vacuum**:
   - Test starting, pausing, stopping, and docking from the Home Assistant dashboard.
   - Test the custom `vacuula-map-card` cards and zone cleaning.

---

## Programmatic Usage in Python & Pytest

You can use the server manager and mock robots directly in your own scripts or pytest fixtures:

```python
from tests.dev_server.server_manager import VacuulaServerManager

# Start server in an isolated sandbox context
with VacuulaServerManager(app_version="1.1.0-b9") as server:
    print("Dev server running at:", server.base_url)

    # Spawn and connect a mock Neato robot
    robot = server.add_mock_robot(
        serial="OPS99999-001122334455",
        name="Study Room Bot",
        installer_version="1.1.0-b3",
    )

    # Manipulate robot state
    robot.set_battery(85)
    robot.set_cleaning()

    # Query server snapshot
    snapshot = server.get_robots_snapshot()
    assert snapshot[robot.serial]["connected"] is True
```

---

## Repository Discovery & Auto-Cloning

The server manager resolves the Vacuula repository automatically in the following order:

1. Path supplied via `--repo` or constructor argument.
2. `VACUULA_REPO_PATH` or `VACUULA_DIR` environment variables.
3. Sibling directory `../vacuula` (standard for developers cloning both repositories).
4. Project-local `.dev_env/vacuula`.
5. User cache directory `~/.cache/hass-vacuula/vacuula`.
6. If no repository is found, it automatically shallow-clones the upstream repository into `~/.cache/hass-vacuula/vacuula`.

Contributors do not need to manually clone or configure paths to begin testing.
