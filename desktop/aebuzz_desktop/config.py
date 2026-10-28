"""Settings stored in %APPDATA%\\AE Buzz\\config.json."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_SERVER_URL = "http://127.0.0.1:8000"


def config_path() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "AE Buzz" / "config.json"


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

    @property
    def paired(self) -> bool:
        return bool(self.pair_id and self.desktop_secret)

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
