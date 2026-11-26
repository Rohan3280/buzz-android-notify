"""Settings stored in %APPDATA%\\AE Buzz\\config.json."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_SERVER_URL = "http://127.0.0.1:8000"

# Where the Buzz desktop apps (Buzz Foundation, then the original Buzz) keep their
# browser storage, which includes the Buzz server address you signed in to.
_BUZZ_STORAGE_DIRS = (
    r"xyz.block.buzz.desktop\EBWebView\Default\Local Storage\leveldb",
    r"xyz.block.buzz.app\EBWebView\Default\Local Storage\leveldb",
)
# A bare server origin; addresses with a path (e.g. .../pair) are other endpoints.
_RELAY_URL_RE = re.compile(rb"wss://[A-Za-z0-9.-]+(?::\d+)?(?![A-Za-z0-9./:-])")


def config_path() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "AE Buzz" / "config.json"


def relay_url_from_storage(blobs: list[bytes]) -> str | None:
    """The most recently written Buzz server address: blobs are newest first."""
    for blob in blobs:
        found = _RELAY_URL_RE.findall(blob)
        if found:
            return found[-1].decode("ascii")
    return None


def detect_buzz_relay_url() -> str | None:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    for rel in _BUZZ_STORAGE_DIRS:
        folder = local / rel
        try:
            files = sorted(
                (p for p in folder.iterdir() if p.suffix in (".log", ".ldb")),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            blobs = [p.read_bytes() for p in files]
        except OSError:
            continue
        url = relay_url_from_storage(blobs)
        if url:
            return url
    return None


@dataclass
class Config:
    server_url: str = DEFAULT_SERVER_URL
    pair_id: str | None = None
    desktop_secret: str | None = None
    paused: bool = False
    # Set only on a laptop that also hosts the relay server; the tray then starts and stops it.
    local_server_dir: str | None = None
    firebase_key_path: str | None = None
    firebase_app_config_path: str | None = None  # google-services.json
    # Optional override; normally detected from the Buzz desktop app.
    buzz_relay_url: str | None = None

    @property
    def paired(self) -> bool:
        return bool(self.pair_id and self.desktop_secret)

    def resolve_buzz_relay_url(self) -> str | None:
        return (self.buzz_relay_url or "").strip().rstrip("/") or detect_buzz_relay_url()

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or config_path()
        try:
            # utf-8-sig: Windows PowerShell 5 writes UTF-8 files with a BOM.
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, path: Path | None = None) -> None:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(path)

    def clear_pairing(self) -> None:
        self.pair_id = None
        self.desktop_secret = None
