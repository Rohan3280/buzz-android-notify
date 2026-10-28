"""Runs the relay server alongside the tray app when this laptop hosts it."""
from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

import httpx

from .config import Config, config_path

log = logging.getLogger(__name__)

STARTUP_TIMEOUT_SECONDS = 20


def _healthy(server_url: str) -> bool:
    try:
        return httpx.get(f"{server_url}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


class LocalServer:
    """Starts the server only if it isn't already running, and stops only what it started."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._process: subprocess.Popen | None = None
        self._log_file = None

    @property
    def enabled(self) -> bool:
        return bool(self._config.local_server_dir)

    def ensure_running(self) -> str | None:
        """Returns an error message, or None once the server answers."""
        if not self.enabled or _healthy(self._config.server_url):
            return None
        server_dir = Path(self._config.local_server_dir)
        python = server_dir / ".venv" / "Scripts" / "python.exe"
        if not python.exists():
            return f"Relay server not found at {server_dir}"
        env = dict(os.environ, AEBUZZ_DB="aebuzz.db")
        if self._config.firebase_key_path:
            env["GOOGLE_APPLICATION_CREDENTIALS"] = self._config.firebase_key_path
        if self._config.firebase_app_config_path:
            env["AEBUZZ_FIREBASE_APP_CONFIG"] = self._config.firebase_app_config_path
        self._log_file = open(config_path().with_name("server.log"), "a", encoding="utf-8")
        self._process = subprocess.Popen(
            [str(python), "-m", "aebuzz_server"],
            cwd=server_dir,
            env=env,
            stdout=self._log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                return f"Relay server exited (code {self._process.returncode}); see server.log"
            if _healthy(self._config.server_url):
                log.info("relay server started (pid %s)", self._process.pid)
                return None
            time.sleep(0.5)
        return "Relay server didn't start in time; see server.log"

    def stop(self) -> None:
        if self._process is None or self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
        if self._log_file is not None:
            self._log_file.close()
