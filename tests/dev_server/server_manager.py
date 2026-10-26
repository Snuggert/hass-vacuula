"""Vacuula dev server runner and lifecycle manager.

Spawns and controls actual Vacuula Server instances in an isolated sandbox,
supporting auto-discovery/cloning of upstream Vacuula, release targeting,
and mock Neato robot device connections.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .mock_neato import MockNeatoRobot

logger = logging.getLogger(__name__)

# Repository root of hass-vacuula
REPO_ROOT = Path(__file__).resolve().parents[2]

# Default upstream git repository for auto-cloning
DEFAULT_UPSTREAM_GIT_URL = (
    os.environ.get("VACUULA_GIT_URL") or "https://github.com/vacuula/vacuula.git"
)

# Default cache directory for auto-cloned Vacuula repo (kept inside project directory, git-ignored)
DEFAULT_CACHE_DIR = REPO_ROOT / ".cache" / "vacuula"


def ensure_uv_available() -> str:
    """Ensure that the uv binary is available on PATH or in standard user locations."""
    uv_bin = shutil.which("uv")
    if uv_bin:
        return uv_bin

    common_paths = [
        Path.home() / ".local" / "bin" / "uv",
        Path.home() / ".cargo" / "bin" / "uv",
        Path("/usr/local/bin/uv"),
        Path("/usr/bin/uv"),
    ]
    for p in common_paths:
        if p.is_file() and os.access(p, os.X_OK):
            current_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{p.parent}:{current_path}"
            logger.info("Found uv at %s; added to PATH", p)
            return str(p)

    raise RuntimeError(
        "The 'uv' package manager is required to run the Vacuula dev server.\n"
        "Please install it using:\n"
        "  curl -LsSf https://astral.sh/uv/install.sh | sh\n"
        "or: pip install uv"
    )


def resolve_or_clone_vacuula_repo(
    custom_path: str | Path | None = None,
    auto_clone: bool = True,
    git_url: str | None = None,
) -> Path:
    """Resolve local Vacuula repository path or automatically clone from upstream.

    Search priority:
      1. Explicit custom_path argument
      2. VACUULA_REPO_PATH or VACUULA_DIR environment variables
      3. Sibling directory '../vacuula'
      4. Project cache directory '.cache/vacuula'
      5. Local dev directory '.dev_env/vacuula'
      6. Automatic git clone to project cache directory (if auto_clone=True)
    """
    candidates: list[Path] = []

    if custom_path:
        candidates.append(Path(custom_path).resolve())

    env_path = os.environ.get("VACUULA_REPO_PATH") or os.environ.get("VACUULA_DIR")
    if env_path:
        candidates.append(Path(env_path).resolve())

    # Sibling directory check (e.g. ~/projects/hass-vacuula & ~/projects/vacuula)
    sibling_path = (REPO_ROOT.parent / "vacuula").resolve()
    candidates.append(sibling_path)

    # Local project dev directory
    local_dev = (REPO_ROOT / ".dev_env" / "vacuula").resolve()
    candidates.append(local_dev)

    # User cache directory
    candidates.append(DEFAULT_CACHE_DIR.resolve())

    for candidate in candidates:
        if candidate.is_dir():
            server_dir = (
                candidate / "server" if (candidate / "server").is_dir() else candidate
            )
            if (server_dir / "pyproject.toml").is_file() or (
                server_dir / "src" / "vacuula_server"
            ).is_dir():
                logger.debug("Resolved Vacuula repository at: %s", candidate)
                return candidate

    if not auto_clone:
        raise FileNotFoundError(
            "Could not locate a Vacuula server repository in any of the search locations:\n"
            + "\n".join(f" - {p}" for p in candidates)
            + "\nSet VACUULA_REPO_PATH or pass --repo <path> to specify the location."
        )

    # Auto-clone into user cache
    clone_target = DEFAULT_CACHE_DIR.resolve()
    clone_url = git_url or DEFAULT_UPSTREAM_GIT_URL
    clone_target.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Vacuula repository not found locally. Auto-cloning %s into %s...",
        clone_url,
        clone_target,
    )
    subprocess.run(
        ["git", "clone", "--depth", "50", clone_url, str(clone_target)],
        check=True,
    )
    return clone_target


def _find_free_port() -> int:
    """Find an available unprivileged TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class VacuulaServerManager:
    """Manages an isolated real Vacuula Server instance for testing and dev."""

    def __init__(
        self,
        vacuula_dir: str | Path | None = None,
        port: int = 0,
        app_version: str = "1.1.0-b9",
        min_installer_version: str | None = "1.1.0-b3",
        release_ref: str | None = None,
        host: str = "127.0.0.1",
        data_dir: str | Path | None = None,
        log_level: str = "INFO",
        auto_clone: bool = True,
    ) -> None:
        """Initialize the server manager."""
        ensure_uv_available()
        self.repo_dir = resolve_or_clone_vacuula_repo(
            custom_path=vacuula_dir,
            auto_clone=auto_clone,
        )
        self.server_dir = (
            self.repo_dir / "server"
            if (self.repo_dir / "server").is_dir()
            else self.repo_dir
        )
        self.port = port or _find_free_port()
        self.host = host
        self.app_version = app_version
        self.min_installer_version = min_installer_version
        self.release_ref = release_ref
        self.log_level = log_level

        self._custom_data_dir = Path(data_dir).resolve() if data_dir else None
        self._temp_dir: tempfile.TemporaryDirectory | None = None
        self.work_dir: Path | None = None
        self.data_dir: Path | None = None
        self.db_path: Path | None = None
        self._worktree_path: Path | None = None

        self._process: subprocess.Popen | None = None
        self._robots: list[MockNeatoRobot] = []

    @property
    def base_url(self) -> str:
        """Return base HTTP URL for Vacuula server."""
        return f"http://{self.host}:{self.port}"

    @property
    def is_running(self) -> bool:
        """Return True if server process is active."""
        return self._process is not None and self._process.poll() is None

    def setup(self) -> None:
        """Prepare sandbox directory, SSL certificates, launcher script, and database."""
        if self._custom_data_dir:
            self.work_dir = self._custom_data_dir
            self.work_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._temp_dir = tempfile.TemporaryDirectory(prefix="vacuula_dev_")
            self.work_dir = Path(self._temp_dir.name)

        # Handle release ref worktree if targeting a specific git commit or tag
        if self.release_ref and self.release_ref.lower() not in (
            "latest",
            "current",
            "head",
        ):
            self._worktree_path = self.work_dir / "repo_checkout"
            try:
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(self.repo_dir),
                        "worktree",
                        "add",
                        "--detach",
                        str(self._worktree_path),
                        self.release_ref,
                    ],
                    check=True,
                    capture_output=True,
                )
                self.server_dir = (
                    self._worktree_path / "server"
                    if (self._worktree_path / "server").is_dir()
                    else self._worktree_path
                )
                logger.info(
                    "Checked out Vacuula ref %s to isolated worktree", self.release_ref
                )
            except Exception as ex:
                logger.warning(
                    "Could not create git worktree for ref %s: %s; falling back to launcher version override",
                    self.release_ref,
                    ex,
                )

        self.data_dir = self.work_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "uploads" / "maps").mkdir(parents=True, exist_ok=True)
        ssl_dir = self.data_dir / "ssl"
        ssl_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.data_dir / "vacuula.db"

        # Copy existing SSL certs from server directory if present, else let server generate
        src_ssl = self.server_dir / "data" / "ssl"
        if src_ssl.is_dir():
            for cert_file in src_ssl.glob("*"):
                shutil.copy(cert_file, ssl_dir / cert_file.name)

        # Generate entrypoint launcher script
        launcher_path = self.work_dir / "run_vacuula.py"
        min_ver_code = (
            f"'{self.min_installer_version}'"
            if self.min_installer_version is not None
            else "None"
        )
        launcher_content = f"""# Auto-generated Vacuula Server Launcher
import sys
import types
from pathlib import Path

# Pre-populate build version before package imports
bv = types.ModuleType("vacuula_server._build_version")
bv.APP_VERSION = "{self.app_version}"
sys.modules["vacuula_server._build_version"] = bv

# Configure isolated directories
data_dir = Path(r"{self.data_dir}")
import vacuula_server.constants as _c
_c.APP_VERSION = "{self.app_version}"
_c.MINIMUM_INSTALLER_VERSION = {min_ver_code}
_c.DATA_DIR = data_dir
_c.DB_PATH = data_dir / "vacuula.db"
_c.SSL_DIR = data_dir / "ssl"
_c.CERT = _c.SSL_DIR / "cert.pem"
_c.KEY = _c.SSL_DIR / "privkey.pem"
_c.UPLOADS_DIR = data_dir / "uploads"
_c.MAPS_DIR = _c.UPLOADS_DIR / "maps"

import vacuula_server.handlers.app as _app
_app.APP_VERSION = "{self.app_version}"
_app.MINIMUM_INSTALLER_VERSION = {min_ver_code}

import vacuula_server.version as _v
_v.MINIMUM_INSTALLER_VERSION = {min_ver_code}

import vacuula_server.db as _db
_db.DB_PATH = _c.DB_PATH
_db.DATABASE_URL = f"sqlite:///{{_c.DB_PATH}}"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
_db.engine = create_engine(_db.DATABASE_URL, echo=False)
_db.SessionLocal = sessionmaker(bind=_db.engine, expire_on_commit=False, class_=Session)

# Run Alembic migrations on sandbox database
from alembic.config import Config
from alembic import command
alembic_cfg = Config(str(_c.ALEMBIC_INI))
alembic_cfg.set_main_option("sqlalchemy.url", _db.DATABASE_URL)
command.upgrade(alembic_cfg, "head")

import vacuula_server
vacuula_server.main()
"""
        launcher_path.write_text(launcher_content, encoding="utf-8")

    def start(self, timeout: float = 15.0) -> None:
        """Start the Vacuula dev server and wait until healthy."""
        if self.is_running:
            return

        if self.work_dir is None:
            self.setup()

        launcher_path = self.work_dir / "run_vacuula.py"

        env = os.environ.copy()
        env["GEN3_ENABLED"] = "false"
        env["GEN4_ENABLED"] = "false"
        env["MDNS_ENABLED"] = "false"
        env["VACUULA_PORT"] = str(self.port)
        env["HOST_IP"] = self.host
        env["LOG_LEVEL"] = self.log_level

        cmd = [
            "uv",
            "run",
            "--project",
            str(self.server_dir),
            "python",
            str(launcher_path),
        ]

        logger.info(
            "Launching Vacuula dev server (port %d, version %s)...",
            self.port,
            self.app_version,
        )

        self._process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for health check
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            if self._process.poll() is not None:
                _, stderr = self._process.communicate()
                raise RuntimeError(
                    f"Vacuula server process exited prematurely with code {self._process.returncode}: {stderr.decode()}"
                )
            try:
                with urllib.request.urlopen(
                    f"{self.base_url}/api/server", timeout=1.0
                ) as resp:
                    if resp.status == 200:
                        logger.info("Vacuula dev server is ready at %s", self.base_url)
                        return
            except (urllib.error.URLError, ConnectionError, OSError) as err:
                last_error = err
                time.sleep(0.3)

        self.stop()
        raise TimeoutError(
            f"Vacuula server did not become ready within {timeout}s: {last_error}"
        )

    def stop(self) -> None:
        """Stop server process, disconnect robots, and clean up temporary directory."""
        # Disconnect all connected mock robots
        for robot in list(self._robots):
            with contextlib.suppress(Exception):
                robot.disconnect()
        self._robots.clear()

        # Stop Vacuula server process
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=3.0)
            except (subprocess.TimeoutExpired, OSError):
                with contextlib.suppress(OSError):
                    self._process.kill()
                    self._process.wait(timeout=2.0)
            self._process = None
            logger.info("Vacuula dev server stopped.")

        # Clean git worktree if one was created
        if self._worktree_path is not None and self._worktree_path.exists():
            with contextlib.suppress(Exception):
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(self.repo_dir),
                        "worktree",
                        "remove",
                        "--force",
                        str(self._worktree_path),
                    ],
                    capture_output=True,
                )
            self._worktree_path = None

        # Clean temporary sandbox
        if self._temp_dir is not None:
            with contextlib.suppress(OSError):
                self._temp_dir.cleanup()
            self._temp_dir = None
            self.work_dir = None

    def add_mock_robot(
        self,
        serial: str = "OPS12345-001122334455",
        name: str = "Mock Neato D7",
        installer_version: str = "1.1.0-b3",
        secret_key: str = "mock_secret_key_12345",
        model: str = "BotVacD7Connected",
        auto_connect: bool = True,
    ) -> MockNeatoRobot:
        """Create, link, and optionally connect a mock Neato robot to this server."""
        if not self.is_running:
            raise RuntimeError("Vacuula server must be running before adding a robot")

        robot = MockNeatoRobot(
            serial=serial,
            name=name,
            secret_key=secret_key,
            installer_version=installer_version,
            model=model,
        )

        if not robot.link(self.host, self.port):
            raise RuntimeError(f"Failed to link mock robot {serial} to {self.base_url}")

        if auto_connect:
            if not robot.connect(self.host, self.port):
                raise RuntimeError(
                    f"Failed to connect mock robot {serial} command channel"
                )
            # Give server a moment to register connection
            time.sleep(0.5)

        self._robots.append(robot)
        return robot

    def get_server_info(self) -> dict[str, Any]:
        """Fetch GET /api/server from the running server."""
        with urllib.request.urlopen(f"{self.base_url}/api/server", timeout=2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_robots_snapshot(self) -> dict[str, Any]:
        """Fetch GET /api/robots from the running server."""
        with urllib.request.urlopen(f"{self.base_url}/api/robots", timeout=2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def __enter__(self) -> VacuulaServerManager:
        """Context manager entrance."""
        self.setup()
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()
