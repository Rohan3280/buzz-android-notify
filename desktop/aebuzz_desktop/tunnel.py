"""A temporary Cloudflare quick tunnel, so the phone can reach the relay server while pairing.

Only used during "Pair phone…": the phone talks to the server once to pair, and after that
notifications go laptop → Firebase → phone. Needs cloudflared (winget install Cloudflare.cloudflared).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlparse


log = logging.getLogger(__name__)

TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
REGISTERED_MARKER = "Registered tunnel connection"
START_TIMEOUT_SECONDS = 60


class TunnelError(Exception):
    pass


def is_local_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host in ("localhost", "::1") or host.startswith("127.")


def find_cloudflared() -> str | None:
    found = shutil.which("cloudflared")
    if found:
        return found
    # Installed after AE Buzz started, so not on this process's PATH yet.
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "cloudflared" / "cloudflared.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "cloudflared" / "cloudflared.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe",
    ]
    return next((str(p) for p in candidates if p.is_file()), None)


class QuickTunnel:
    def __init__(self, local_url: str, executable: str | None = None) -> None:
        self._local_url = local_url
        self._executable = executable
        self._process: subprocess.Popen | None = None

    def start(self) -> str:
        """Starts the tunnel and returns its public https URL once it answers."""
        exe = self._executable or find_cloudflared()
        if not exe:
            raise TunnelError("cloudflared isn't installed")
        self._process = subprocess.Popen(
            [exe, "tunnel", "--no-autoupdate", "--url", self._local_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        found: list[str] = []
        registered = threading.Event()

        def read_log() -> None:
            # cloudflared logs to stderr; keep draining it so the pipe never fills up.
            for line in self._process.stderr:
                if not found and (match := TUNNEL_URL_RE.search(line)):
                    found.append(match.group(0))
                if found and REGISTERED_MARKER in line:
                    registered.set()
            registered.set()  # cloudflared exited

        threading.Thread(target=read_log, name="cloudflared-log", daemon=True).start()
        # Don't look the new address up from this laptop to check it: asking before Cloudflare
        # has published it makes Windows cache "not found" for minutes. The phone looks it up
        # itself, after the code is scanned.
        if not registered.wait(START_TIMEOUT_SECONDS) or not found or self._process.poll() is not None:
            self.stop()
            raise TunnelError("cloudflared didn't start a tunnel")
        log.info("pairing tunnel open at %s", found[0])
        return found[0]

    def stop(self) -> None:
        if self._process is None or self._process.poll() is not None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
        log.info("pairing tunnel closed")
