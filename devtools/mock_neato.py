"""Mock Neato robot hardware and protocol simulator.

Simulates Neato Botvac robots (Gen3 HTTP chunked protocol) interacting with
Vacuula Server's robot endpoints (/links and /vendors/neato/login).
"""

from __future__ import annotations

import contextlib
import json
import logging
import select
import socket
import threading
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def build_sample_floormap_rle(width: int = 64, height: int = 64) -> dict[str, Any]:
    """Generate a realistic sample RLE floorplan payload for testing & sandbox."""
    grid = [0] * (width * height)
    # Draw an L-shaped floor plan with walls (2) around free floor (1)
    for y in range(8, 56):
        max_x = 56 if y >= 24 else 36
        for x in range(8, max_x):
            is_wall = (
                x in (8, max_x - 1)
                or y in (8, 55)
                or (y == 24 and x >= 35)
                or (x == 32 and 24 < y < 44)  # internal room divider wall with doorway
            )
            grid[y * width + x] = 2 if is_wall else 1

    # Encode flat grid into [[val, count], ...] RLE
    rle: list[list[int]] = []
    for val in grid:
        if rle and rle[-1][0] == val:
            rle[-1][1] += 1
        else:
            rle.append([val, 1])

    return {
        "width": width,
        "height": height,
        "rle": rle,
        "dock": {"pixel_x": 12, "pixel_y": 32},
        "base": [12 / width, 32 / height],
    }


def build_sample_runmap_rle(width: int = 64, height: int = 64) -> dict[str, Any]:
    """Generate a realistic sample RLE cleaning run map payload."""
    # Default background value for runmap is 128
    grid = [128] * (width * height)
    for y in range(10, 54):
        max_x = 54 if y >= 26 else 34
        for x in range(10, max_x):
            if (y - 10) % 3 == 0:
                grid[y * width + x] = 150  # Robot trajectory line
            else:
                grid[y * width + x] = 3  # Cleaned area overlay
    # Dock marker at (12, 32)
    grid[32 * width + 12] = 100

    rle: list[list[int]] = []
    for val in grid:
        if rle and rle[-1][0] == val:
            rle[-1][1] += 1
        else:
            rle.append([val, 1])

    return {
        "width": width,
        "height": height,
        "rle": rle,
    }


class MockNeatoRobot:
    """Simulates a Neato Botvac robot connected to Vacuula Server.

    Manages robot state, handles robot command dispatch, replies to Nucleo HTTP
    chunked commands, and emits events over the socket connection.
    """

    def __init__(
        self,
        serial: str = "OPS12345-001122334455",
        name: str = "Mock Botvac D7",
        secret_key: str = "mock_secret_key_12345",
        installer_version: str = "1.1.0-b3",
        model: str = "BotVacD7Connected",
        firmware: str = "4.5.3-189",
    ) -> None:
        """Initialize the simulated robot."""
        self.serial = serial
        self.name = name
        self.secret_key = secret_key
        self.installer_version = installer_version
        self.model = model
        self.firmware = firmware

        # Robot state machine
        self.state: int = 1  # 1=IDLE, 2=BUSY, 3=PAUSED, 4=ERROR
        self.action: int = 0  # 0=NONE, 1=HOUSE, 2=SPOT, 4=DOCKING, 11=MAP, 12=EXPLORING
        self.charge: int = 95
        self.is_docked: bool = True
        self.is_charging: bool = False
        self.is_schedule_enabled: bool = True
        self.dock_has_been_seen: bool = True
        self.alert: str | None = None
        self.error: str | None = None

        # Cleaning parameters
        self.cleaning_category: int = 4  # 2=HOUSE, 3=SPOT, 4=MAP
        self.cleaning_mode: int = 2  # 1=ECO, 2=TURBO
        self.navigation_mode: int = 1  # 1=NORMAL, 2=EXTRA_CARE, 3=DEEP
        self.spot_width: int = 200
        self.spot_height: int = 200

        # Cleaning parameters / zone boundaries
        self.boundaries: list[dict[str, Any]] = [
            {
                "id": "bnd-kitchen",
                "name": "Kitchen",
                "type": "polygon",
                "color": "#38bdf8",
                "enabled": True,
                "vertices": [
                    [0.14, 0.14],
                    [0.54, 0.14],
                    [0.54, 0.45],
                    [0.14, 0.45],
                ],
            },
            {
                "id": "bnd-living-room",
                "name": "Living Room",
                "type": "polygon",
                "color": "#4ade80",
                "enabled": True,
                "vertices": [
                    [0.50, 0.39],
                    [0.86, 0.39],
                    [0.86, 0.85],
                    [0.50, 0.85],
                ],
            },
            {
                "id": "bnd-nogo-stairs",
                "name": "Stairs",
                "type": "polyline",
                "color": "#ef4444",
                "enabled": True,
                "vertices": [[0.14, 0.82], [0.45, 0.82]],
            },
        ]

        # Connection and threading state
        self._host: str = "127.0.0.1"
        self._port: int = 8050
        self._sock: socket.socket | None = None
        self._connected: bool = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()

        # Telemetry / test assertions
        self.command_history: list[dict[str, Any]] = []
        self.locate_calls: int = 0
        self.last_command: dict[str, Any] | None = None

    @property
    def is_connected(self) -> bool:
        """Return True if currently connected to Vacuula server."""
        return self._connected

    def link(self, host: str, port: int, timeout: float = 5.0) -> bool:
        """Pair and link the robot to Vacuula Server via POST /links."""
        url = f"http://{host}:{port}/links"
        name_payload = (
            f"{self.name}--IV--{self.installer_version}"
            if self.installer_version
            else self.name
        )
        body = json.dumps({"name": name_payload, "secret_key": self.secret_key}).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Accept": "application/vnd.neato.beehive.v1+json",
                "Authorization": f"NEATOBOT {self.serial}:dummy_signature",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                logger.info(
                    "MockNeatoRobot %s linked successfully (status %d)",
                    self.serial,
                    resp.status,
                )
                return resp.status in (200, 201)
        except urllib.error.HTTPError as err:
            logger.error("Failed to link robot %s: HTTP %s", self.serial, err.code)
            return False
        except Exception as ex:
            logger.error("Error linking robot %s: %s", self.serial, ex)
            return False

    def connect(self, host: str, port: int, timeout: float = 5.0) -> bool:
        """Connect persistent command channel to Vacuula Server via POST /vendors/neato/login."""
        if self._connected:
            return True

        self._host = host
        self._port = port
        self._stop_event.clear()
        sock = socket.create_connection((host, port), timeout=timeout)
        request_headers = (
            f"POST /vendors/neato/login HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Accept: application/vnd.neato.cometa.v1\r\n"
            f"Authorization: NEATOBOT {self.serial}:dummy_signature\r\n"
            f"Transfer-Encoding: chunked\r\n\r\n"
        )
        sock.sendall(request_headers.encode("utf-8"))

        # Read HTTP response headers from Vacuula without makefile() so socket
        # buffers never become corrupted across select()/timeout cycles.
        buf = bytearray()
        while b"\r\n\r\n" not in buf:
            data = sock.recv(4096)
            if not data:
                sock.close()
                return False
            buf.extend(data)

        header_bytes, remaining = buf.split(b"\r\n\r\n", 1)
        status_line = header_bytes.split(b"\r\n", 1)[0].decode(
            "utf-8", errors="replace"
        )
        if "200" not in status_line:
            logger.error(
                "MockNeatoRobot %s failed to connect: %s", self.serial, status_line
            )
            sock.close()
            return False

        sock.settimeout(None)
        self._sock = sock
        self._connected = True

        self._thread = threading.Thread(
            target=self._command_loop,
            args=(sock, bytearray(remaining)),
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "MockNeatoRobot %s connected to Vacuula on port %d", self.serial, port
        )
        return True

    def disconnect(self) -> None:
        """Disconnect robot from Vacuula Server."""
        self._stop_event.set()
        self._connected = False
        if self._sock:
            with contextlib.suppress(OSError):
                self._sock.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                self._sock.close()
            self._sock = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("MockNeatoRobot %s disconnected", self.serial)

    def _command_loop(self, sock: socket.socket, buf: bytearray) -> None:
        """Background thread reading chunked command requests from Vacuula."""
        try:
            while not self._stop_event.is_set():
                # Process all complete HTTP chunks already in buf
                while True:
                    crlf_idx = buf.find(b"\r\n")
                    if crlf_idx == -1:
                        break
                    line = bytes(buf[:crlf_idx]).strip()
                    if not line:
                        del buf[: crlf_idx + 2]
                        continue
                    try:
                        chunk_size = int(line, 16)
                    except ValueError:
                        del buf[: crlf_idx + 2]
                        continue

                    if chunk_size == 0:
                        return

                    total_needed = crlf_idx + 2 + chunk_size + 2
                    if len(buf) < total_needed:
                        break

                    payload = bytes(buf[crlf_idx + 2 : crlf_idx + 2 + chunk_size])
                    del buf[:total_needed]
                    if payload:
                        self._process_incoming_chunk(payload)

                # Wait up to 15s for incoming command chunks from Vacuula Server
                try:
                    readable, _, _ = select.select([sock], [], [], 15.0)
                except OSError, ValueError:
                    break

                if self._stop_event.is_set():
                    break

                if not readable:
                    # Periodic keepalive so Vacuula Server's 60s socket timeout never drops the robot
                    self.emit_event("ping")
                    continue

                try:
                    chunk_data = sock.recv(4096)
                except OSError:
                    break
                if not chunk_data:
                    break
                buf.extend(chunk_data)

        except OSError, BrokenPipeError, ConnectionResetError:
            pass
        finally:
            self._connected = False
            with contextlib.suppress(OSError):
                sock.close()

    def _process_incoming_chunk(self, chunk: bytes) -> None:
        """Parse incoming chunk from Vacuula and send appropriate response."""
        # Handle server heartbeat JSON (no CRLF separator)
        if b"\r\n" not in chunk:
            try:
                data = json.loads(chunk.decode("utf-8"))
                if "heartbeat" in data:
                    logger.debug("MockNeatoRobot %s received heartbeat", self.serial)
                    return
            except json.JSONDecodeError:
                return

        # Vacuula commands arrive as: date|signature\r\n{"reqId": "...", "cmd": "..."}
        try:
            _, json_data = chunk.split(b"\r\n", 1)
            cmd_payload = json.loads(json_data.decode("utf-8"))
        except Exception as ex:
            logger.warning("MockNeatoRobot failed to parse chunk %r: %s", chunk, ex)
            return

        req_id = cmd_payload.get("reqId", "1")
        cmd = cmd_payload.get("cmd", "")
        params = cmd_payload.get("params", {})

        with self._lock:
            self.command_history.append(cmd_payload)
            self.last_command = cmd_payload
            reply = self._dispatch_command(cmd, req_id, params)

        self._send_chunk(reply)

    def _dispatch_command(
        self, cmd: str, req_id: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch command to internal handler and update state machine."""
        if cmd == "getRobotState":
            return self._build_state_response(req_id)

        if cmd == "startCleaning":
            self.state = 2  # BUSY
            self.is_docked = False
            self.is_charging = False
            category = int(params.get("category", 4))
            self.cleaning_category = category
            if "mode" in params:
                self.cleaning_mode = int(params["mode"])
            if "navigationMode" in params:
                self.navigation_mode = int(params["navigationMode"])
            if "spotWidth" in params:
                self.spot_width = int(params["spotWidth"])
            if "spotHeight" in params:
                self.spot_height = int(params["spotHeight"])

            if category == 3:
                self.action = 2  # SPOT_CLEANING
            elif category == 4 or "boundaryId" in params or "boundaryIds" in params:
                self.action = 11  # MAP_CLEANING
            else:
                self.action = 1  # HOUSE_CLEANING
            return self._build_state_response(req_id)

        if cmd == "pauseCleaning":
            self.state = 3  # PAUSED
            return self._build_state_response(req_id)

        if cmd == "resumeCleaning":
            self.state = 2  # BUSY
            return self._build_state_response(req_id)

        if cmd == "stopCleaning":
            self.state = 1  # IDLE
            self.action = 0  # NONE
            return self._build_state_response(req_id)

        if cmd == "sendToBase":
            self.state = 1  # IDLE
            self.action = 4  # DOCKING
            self.is_docked = True
            self.is_charging = True
            return self._build_state_response(req_id)

        if cmd == "findMe":
            self.locate_calls += 1
            return {"reqId": req_id, "result": "ok", "data": {}}

        if cmd == "dismissCurrentAlert":
            self.alert = None
            return self._build_state_response(req_id)

        if cmd == "enableSchedule":
            self.is_schedule_enabled = True
            return self._build_state_response(req_id)

        if cmd == "disableSchedule":
            self.is_schedule_enabled = False
            return self._build_state_response(req_id)

        if cmd == "getMapBoundaries":
            return {
                "reqId": req_id,
                "result": "ok",
                "data": {"boundaries": self.boundaries},
            }

        if cmd == "setMapBoundaries":
            self.boundaries = params.get("boundaries", self.boundaries)
            return {
                "reqId": req_id,
                "result": "ok",
                "data": {"boundaries": self.boundaries},
            }

        if cmd == "startPersistentMapExploration":
            self.state = 2  # BUSY
            self.action = 12  # EXPLORING_MAP
            self.is_docked = False
            return self._build_state_response(req_id)

        # Unknown or unhandled command
        return {
            "reqId": req_id,
            "result": "ok",
            "data": {},
        }

    def _build_state_response(self, req_id: str) -> dict[str, Any]:
        """Construct full standard Neato robot state payload."""
        return {
            "version": 1,
            "reqId": str(req_id),
            "result": "ok",
            "error": self.error,
            "alert": self.alert,
            "state": self.state,
            "action": self.action,
            "cleaning": {
                "category": self.cleaning_category,
                "mode": self.cleaning_mode,
                "modifier": 1,
                "navigationMode": self.navigation_mode,
                "spotWidth": self.spot_width,
                "spotHeight": self.spot_height,
            },
            "details": {
                "isCharging": self.is_charging,
                "isDocked": self.is_docked,
                "isScheduleEnabled": self.is_schedule_enabled,
                "dockHasBeenSeen": self.dock_has_been_seen,
                "charge": self.charge,
            },
            "cleanedArea": 38.5 if self.state == 2 else 0.0,
            "availableServices": {
                "houseCleaning": "basic-4",
                "spotCleaning": "basic-3",
                "manualCleaning": "basic-1",
                "easyConnect": "basic-1",
                "schedule": "basic-2",
                "maps": "macro-1",
                "generalInfo": "basic-1",
            },
            "availableCommands": {
                "start": self.state in (1, 3),
                "stop": self.state in (2, 3),
                "pause": self.state == 2,
                "resume": self.state == 3,
                "goToBase": not self.is_docked,
            },
            "meta": {
                "modelName": self.model,
                "firmware": self.firmware,
            },
        }

    def _send_chunk(self, payload_dict: dict[str, Any]) -> None:
        """Send chunk-encoded JSON to Vacuula server."""
        if not self._sock or not self._connected:
            return
        try:
            payload_bytes = json.dumps(payload_dict).encode("utf-8")
            chunk = f"{len(payload_bytes):X}\r\n".encode() + payload_bytes + b"\r\n"
            with self._send_lock:
                self._sock.sendall(chunk)
        except OSError, BrokenPipeError:
            self._connected = False

    def emit_event(self, event_id: str, data: dict[str, Any] | None = None) -> None:
        """Push an asynchronous event to Vacuula Server over the command stream."""
        event_dict: dict[str, Any] = {"eventId": event_id}
        if data:
            event_dict.update(data)
        self._send_chunk(event_dict)

    def push_state_update(self, event_id: str = "stateChanged") -> None:
        """Emit a live state change frame to Vacuula Server (triggers GET /api/robot/<serial>/connect SSE)."""
        state_payload = self._build_state_response("0")
        state_payload.pop("reqId", None)
        state_payload["eventId"] = event_id
        self._send_chunk(state_payload)

    # State manipulation helper methods for tests and interactive dev mode
    def set_battery(self, charge: int, is_charging: bool = False) -> None:
        """Update battery charge percentage and charging status."""
        self.charge = max(0, min(100, int(charge)))
        self.is_charging = is_charging
        self.push_state_update()

    def set_docked(self, is_docked: bool) -> None:
        """Update docked status."""
        self.is_docked = is_docked
        if is_docked:
            self.action = 0
            if self.state == 2:
                self.state = 1
        self.push_state_update()

    def set_cleaning(self, action: int = 1, category: int | None = None) -> None:
        """Trigger cleaning state (BUSY)."""
        self.state = 2
        self.action = action
        if category is not None:
            self.cleaning_category = category
        elif action == 11:
            self.cleaning_category = 4
        elif action == 2:
            self.cleaning_category = 3
        else:
            self.cleaning_category = 2
        self.is_docked = False
        self.is_charging = False
        self.push_state_update()

    def set_exploring(self) -> None:
        """Trigger map exploration state (action=12)."""
        self.state = 2
        self.action = 12
        self.is_docked = False
        self.is_charging = False
        self.push_state_update()

    def finish_cleaning_run(self) -> None:
        """Transition from BUSY cleaning to IDLE Docked + Charging (triggers run refresh)."""
        self.state = 1
        self.action = 0
        self.is_docked = True
        self.is_charging = True
        self.alert = "clean_completed_to_start"
        self.push_state_update()

    def set_schedule(self, enabled: bool) -> None:
        """Toggle schedule enabled state."""
        self.is_schedule_enabled = bool(enabled)
        self.push_state_update()

    def set_dock_seen(self, seen: bool) -> None:
        """Toggle whether the charging dock has been seen."""
        self.dock_has_been_seen = bool(seen)
        self.push_state_update()

    def set_paused(self) -> None:
        """Trigger paused state."""
        self.state = 3
        self.push_state_update()

    def set_idle(self) -> None:
        """Trigger idle state."""
        self.state = 1
        self.action = 0
        self.push_state_update()

    def set_alert(self, alert_code: str | None) -> None:
        """Set or clear robot alert (e.g. dustbin_full)."""
        self.alert = alert_code
        self.push_state_update()

    def set_error(self, error_code: str | None) -> None:
        """Set or clear robot error (e.g. ui_error_brush_stuck)."""
        self.error = error_code
        if error_code:
            self.state = 4  # ERROR
        elif self.state == 4:
            self.state = 1
        self.push_state_update()
