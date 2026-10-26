#!/usr/bin/env python3
"""Standalone runner for the Vacuula developer test environment.

Runs an actual Vacuula Server instance backed by mock Neato robots, allowing
live end-to-end testing with Home Assistant or the Vacuula integration test suite.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
import threading
import time
from pathlib import Path

# Pre-import homeassistant before voluptuous so probatio's install_as_voluptuous()
# never emits a RuntimeWarning.
with contextlib.suppress(ImportError):
    import homeassistant  # noqa: F401

# Ensure repository root is on PYTHONPATH
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.dev_server.mock_neato import MockNeatoRobot  # noqa: E402
from tests.dev_server.sandbox import VacuulaDevSandbox  # noqa: E402
from tests.dev_server.server_manager import VacuulaServerManager  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run an actual Vacuula Server instance with simulated Neato robots for local development."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8050,
        help="Port for the Vacuula dev server HTTP API (default: 8050)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--version",
        type=str,
        default="1.1.0-b9",
        help="Vacuula server release version to report (default: 1.1.0-b9)",
    )
    parser.add_argument(
        "--min-installer",
        type=str,
        default="1.1.0-b3",
        help="Minimum required installer version (default: 1.1.0-b3, use 'none' for older releases)",
    )
    parser.add_argument(
        "--robots",
        type=int,
        default=1,
        help="Number of initial mock robots to spawn and connect (default: 1)",
    )
    parser.add_argument(
        "--robot-installer",
        type=str,
        default="1.1.0-b3",
        help="Installer version string sent by mock robots during linking (default: 1.1.0-b3)",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Path to the Vacuula server repository (default: auto-detected from sibling ../vacuula, VACUULA_REPO_PATH, or auto-cloned)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Custom persistent directory for server data and database (default: temporary directory)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without the interactive CLI prompt (waits until SIGINT/Ctrl+C)",
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        default=True,
        dest="sandbox",
        help="Launch the Full-Stack Integration + Lovelace + Entity Sandbox UI (enabled by default)",
    )
    parser.add_argument(
        "--no-sandbox",
        action="store_false",
        dest="sandbox",
        help="Disable the Full-Stack Integration + Lovelace + Entity Sandbox UI (run only the Vacuula Server and mock robots)",
    )
    parser.add_argument(
        "--sandbox-port",
        type=int,
        default=8124,
        help="Port for the Full-Stack Integration + Lovelace + Entity Sandbox UI (default: 8124)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging output",
    )
    return parser.parse_args()


def print_banner(
    server: VacuulaServerManager,
    robots: list[MockNeatoRobot],
    sandbox: VacuulaDevSandbox | None = None,
) -> None:
    """Print informative welcome banner."""
    print("=" * 74)
    print(f"  VACUULA FULL-STACK DEVELOPER ENVIRONMENT (Release: {server.app_version})")
    print(f"  Vacuula Server: {server.base_url}")
    if sandbox:
        print(
            f"  Lovelace UI:    {sandbox.sandbox_url}  (Map Card + Entity Inspector + Simulator)"
        )
        print(
            f"  HA Integration: custom_components/vacuula ({len(sandbox.entities)} live entities across 7 platforms)"
        )
    print(f"  Database:       {server.db_path}")
    print(f"  Min Installer:  {server.min_installer_version}")
    print(f"  Mock Robots:    {len(robots)} connected")
    for r in robots:
        print(
            f"   - {r.serial}: '{r.name}' (Model: {r.model}, Batt: {r.charge}%, State: {r.state}, Installer: {r.installer_version})"
        )
    print("=" * 74)
    if sandbox:
        print(f"  Open {sandbox.sandbox_url} in your browser to interact with:")
        print("  1. Lovelace <vacuula-map-card> & live configuration editor")
        print(
            "  2. All 22+ real custom_components/vacuula entities (vacuum, image, sensor,"
        )
        print("     binary_sensor, select, switch, button) & Device Registry")
        print("  3. Live Mock Neato Botvac D7 Hardware Simulator (SSE real-time sync)")
    else:
        print("  To test with an external Home Assistant instance:")
        print(f"  1. Configure Vacuula integration to point to: {server.base_url}")
        print("  2. Discovered robots will appear automatically in HA!")
    print("=" * 74)


def print_help() -> None:
    """Print interactive command help."""
    print(
        """
Available interactive commands:
  status                 - Show dev server info, mock robots, and all 25 integration entities
  clean [serial]         - Start map/zone cleaning (BUSY state)
  explore [serial]       - Start persistent map exploration (action=12)
  pause [serial]         - Pause current cleaning
  resume [serial]        - Resume paused cleaning
  stop [serial]          - Stop cleaning (return to IDLE)
  dock [serial]          - Send robot back to charging base
  finish [serial]        - Complete cleaning run and return to dock
  battery [serial] <pct> - Update battery level (0-100)
  alert [serial] <code>  - Trigger an alert (e.g. dustbin_full, maint_brush_change, clear_path)
  error [serial] <code>  - Trigger an error (e.g. ui_error_brush_stuck, ui_error_navigation_stuck)
  clear [serial]         - Clear active alerts and errors
  disconnect [serial]    - Simulate WiFi/server disconnection (Away)
  reconnect [serial]     - Reconnect disconnected robot
  add <name>             - Spawn and link a new mock Neato robot
  help                   - Show this command reference
  quit / exit            - Shutdown dev server and exit
"""
    )


def resolve_robot(
    robots: list[MockNeatoRobot], target: str | None
) -> MockNeatoRobot | None:
    """Find robot by serial, name, or default to first robot."""
    if not robots:
        print("No robots available.")
        return None
    if not target:
        return robots[0]
    for r in robots:
        if r.serial == target or r.name.lower() == target.lower():
            return r
    print(
        f"Robot '{target}' not found. Available serials: {[r.serial for r in robots]}"
    )
    return None


def interactive_loop(
    server: VacuulaServerManager,
    robots: list[MockNeatoRobot],
    sandbox: VacuulaDevSandbox | None = None,
    sandbox_loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """Run interactive REPL loop."""

    def _notify_sandbox() -> None:
        if sandbox is not None and sandbox_loop is not None:
            asyncio.run_coroutine_threadsafe(
                sandbox._async_refresh_runtime(), sandbox_loop
            )

    print("Type 'help' for available commands, or 'quit' to exit.")
    while server.is_running:
        try:
            line = input("vacuula-dev> ").strip()
        except EOFError, KeyboardInterrupt:
            print("\nExiting...")
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("quit", "exit", "q"):
            break

        elif cmd == "help":
            print_help()

        elif cmd == "status":
            try:
                snapshot = server.get_robots_snapshot()
                print("\nServer snapshot (GET /api/robots):")
                print(snapshot)
            except Exception as e:
                print(f"Error fetching snapshot: {e}")
            print("\nLocal mock robots:")
            for r in robots:
                print(
                    f" - {r.serial} [{r.name}]: connected={r.is_connected}, state={r.state}, action={r.action}, charge={r.charge}%, docked={r.is_docked}, alert={r.alert}, error={r.error}"
                )
            if sandbox is not None:
                print(
                    f"\nIntegration entities ({len(sandbox.entities)} loaded across 7 platforms):"
                )
                for ent in sandbox.build_entity_inspector_list():
                    print(
                        f" - {ent['entity_id']:42s} = {ent['state']!r:14s} ({ent['entity_class']})"
                    )

        elif cmd == "clean":
            target = args[0] if args else None
            r = resolve_robot(robots, target)
            if r:
                r.set_cleaning(action=11, category=4)
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) set to CLEANING (state=2).")

        elif cmd == "explore":
            target = args[0] if args else None
            r = resolve_robot(robots, target)
            if r:
                r.set_exploring()
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) set to EXPLORING MAP (action=12).")

        elif cmd == "pause":
            target = args[0] if args else None
            r = resolve_robot(robots, target)
            if r:
                r.set_paused()
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) set to PAUSED (state=3).")

        elif cmd == "resume":
            target = args[0] if args else None
            r = resolve_robot(robots, target)
            if r:
                r.set_cleaning(action=r.action or 11)
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) RESUMED cleaning (state=2).")

        elif cmd == "stop":
            target = args[0] if args else None
            r = resolve_robot(robots, target)
            if r:
                r.set_idle()
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) STOPPED (state=1).")

        elif cmd == "dock":
            target = args[0] if args else None
            r = resolve_robot(robots, target)
            if r:
                r.set_docked(True)
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) DOCKED (is_docked=True, state=1).")

        elif cmd == "finish":
            target = args[0] if args else None
            r = resolve_robot(robots, target)
            if r:
                r.finish_cleaning_run()
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) COMPLETED cleaning run and docked.")

        elif cmd == "battery":
            if not args:
                print("Usage: battery [serial] <percentage>")
                continue
            pct = int(args[-1]) if args[-1].isdigit() else 100
            target = args[0] if len(args) > 1 else None
            r = resolve_robot(robots, target)
            if r:
                r.set_battery(pct)
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) battery set to {pct}%.")

        elif cmd == "alert":
            if not args:
                print("Usage: alert [serial] <alert_code>")
                continue
            code = args[-1]
            target = args[0] if len(args) > 1 else None
            r = resolve_robot(robots, target)
            if r:
                r.set_alert(code)
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) alert set to '{code}'.")

        elif cmd == "error":
            if not args:
                print("Usage: error [serial] <error_code>")
                continue
            code = args[-1]
            target = args[0] if len(args) > 1 else None
            r = resolve_robot(robots, target)
            if r:
                r.set_error(code)
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) error set to '{code}' (state=4).")

        elif cmd == "clear":
            target = args[0] if args else None
            r = resolve_robot(robots, target)
            if r:
                r.set_alert(None)
                r.set_error(None)
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) cleared alerts and errors.")

        elif cmd == "disconnect":
            target = args[0] if args else None
            r = resolve_robot(robots, target)
            if r:
                r._user_disconnected = True  # type: ignore[attr-defined]  # noqa: SLF001
                r.disconnect()
                _notify_sandbox()
                print(f"Robot {r.serial} ({r.name}) disconnected from server.")

        elif cmd == "reconnect":
            target = args[0] if args else None
            r = resolve_robot(robots, target)
            if r:
                r._user_disconnected = False  # type: ignore[attr-defined]  # noqa: SLF001
                if r.connect(server.host, server.port):
                    _notify_sandbox()
                    print(f"Robot {r.serial} ({r.name}) reconnected!")
                else:
                    print(f"Failed to reconnect {r.serial}.")

        elif cmd == "add":
            name = " ".join(args) if args else f"Mock Bot {len(robots) + 1}"
            idx = len(robots) + 1
            serial = f"OPS{idx:05d}-00112233{idx:04d}"
            try:
                new_robot = server.add_mock_robot(
                    serial=serial,
                    name=name,
                    installer_version="1.1.0-b3",
                )
                robots.append(new_robot)
                if sandbox is not None and sandbox_loop is not None:
                    fut = asyncio.run_coroutine_threadsafe(
                        sandbox._setup_real_integration_entities(), sandbox_loop
                    )
                    fut.result(timeout=5.0)
                    _notify_sandbox()
                print(f"Spawned, linked, and connected new robot {serial} ('{name}').")
            except Exception as e:
                print(f"Error adding robot: {e}")

        else:
            print(f"Unknown command: '{cmd}'. Type 'help' for command list.")


def main() -> None:
    """Main CLI entrypoint."""
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    min_installer = None if args.min_installer.lower() == "none" else args.min_installer

    server = VacuulaServerManager(
        vacuula_dir=args.repo,
        port=args.port,
        host=args.host,
        app_version=args.version,
        min_installer_version=min_installer,
        data_dir=args.data_dir,
    )

    try:
        print(f"Starting Vacuula Dev Server on http://{args.host}:{args.port}...")
        server.setup()
        server.start()
    except Exception as e:
        print(f"Failed to start Vacuula dev server: {e}", file=sys.stderr)
        sys.exit(1)

    robots: list[MockNeatoRobot] = []
    robot_names = ["Living Room Bot", "Hallway Bot", "Office Bot", "Upstairs Bot"]
    for i in range(args.robots):
        serial = f"OPS{i + 1:05d}-0011223344{i + 1:02d}"
        name = robot_names[i] if i < len(robot_names) else f"Mock Neato D7 #{i + 1}"
        try:
            r = server.add_mock_robot(
                serial=serial,
                name=name,
                installer_version=args.robot_installer,
            )
            robots.append(r)
        except Exception as e:
            print(f"Warning: could not add robot {serial}: {e}", file=sys.stderr)

    sandbox_loop: asyncio.AbstractEventLoop | None = None
    sandbox: VacuulaDevSandbox | None = None

    if args.sandbox:
        sandbox = VacuulaDevSandbox(
            vacuula_url=server.base_url,
            server_manager=server,
            host=args.host,
            port=args.sandbox_port,
        )
        sandbox_loop = asyncio.new_event_loop()
        ready_ev = threading.Event()

        def _run_sandbox() -> None:
            assert sandbox_loop is not None and sandbox is not None
            asyncio.set_event_loop(sandbox_loop)
            sandbox_loop.run_until_complete(sandbox.async_start())
            ready_ev.set()
            sandbox_loop.run_forever()

        threading.Thread(target=_run_sandbox, daemon=True).start()
        ready_ev.wait(timeout=5.0)

    print_banner(server, robots, sandbox=sandbox)

    try:
        if args.non_interactive:
            print("Running in non-interactive mode. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
        else:
            interactive_loop(server, robots, sandbox=sandbox, sandbox_loop=sandbox_loop)
    except KeyboardInterrupt:
        print("\nShutdown signal received.")
    finally:
        if sandbox is not None and sandbox_loop is not None:
            fut = asyncio.run_coroutine_threadsafe(sandbox.async_stop(), sandbox_loop)
            with (
                sys.exc_info()[0]
                if False
                else __import__("contextlib").suppress(Exception)
            ):
                fut.result(timeout=3.0)
            sandbox_loop.call_soon_threadsafe(sandbox_loop.stop)
        print("Stopping Vacuula dev server and mock robots...")
        server.stop()
        print("Vacuula dev server stopped cleanly.")


if __name__ == "__main__":
    main()
