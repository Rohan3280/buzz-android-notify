"""Talks to the relay server and forwards notifications with retry."""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable

import httpx

from .config import Config
from .toasts import Toast

log = logging.getLogger(__name__)

MAX_QUEUED = 100
MAX_BACKOFF_SECONDS = 300


@dataclass
class NewPairing:
    pair_id: str
    desktop_secret: str
    qr_payload: str
    phone_url: str


class RelayClient:
    def __init__(self, server_url: str, timeout: float = 10.0) -> None:
        self._http = httpx.Client(base_url=server_url, timeout=timeout)

    def create_pairing(self) -> NewPairing:
        r = self._http.post("/pairings")
        r.raise_for_status()
        body = r.json()
        # The phone must reach the server; localhost only works for the laptop itself.
        phone_url = body.get("public_url") or str(self._http.base_url).rstrip("/")
        payload = {"v": 1, "server": phone_url, "pair": body["pair_id"], "token": body["pair_token"]}
        if body.get("firebase"):
            # Lets one prebuilt APK connect to whichever Firebase project this server uses.
            payload["fb"] = body["firebase"]
        qr = json.dumps(payload, separators=(",", ":"))
        return NewPairing(body["pair_id"], body["desktop_secret"], qr, phone_url)

    def status(self, pair_id: str, secret: str) -> dict | None:
        """None means the pairing no longer exists."""
        r = self._http.get(f"/pairings/{pair_id}", headers=_auth(secret))
        if r.status_code == 410:
            return None
        r.raise_for_status()
        return r.json()

    def notify(self, pair_id: str, secret: str, toast: Toast) -> int:
        r = self._http.post(
            f"/pairings/{pair_id}/notify",
            json={"title": toast.title, "body": toast.body, "app": "Buzz", "ts": time.time()},
            headers=_auth(secret),
        )
        return r.status_code

    def unpair(self, pair_id: str, secret: str) -> None:
        self._http.delete(f"/pairings/{pair_id}", headers=_auth(secret))


def _auth(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


class Forwarder:
    """Background queue that delivers notifications, retrying while the server is unreachable."""

    def __init__(
        self,
        config: Config,
        client_factory: Callable[[str], RelayClient],
        on_status: Callable[[str], None],
        on_unpaired: Callable[[], None],
    ) -> None:
        self._config = config
        self._client_factory = client_factory
        self._on_status = on_status
        self._on_unpaired = on_unpaired
        self._queue: queue.Queue[Toast] = queue.Queue(maxsize=MAX_QUEUED)
        self._thread = threading.Thread(target=self._run, name="forwarder", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def submit(self, toast: Toast) -> None:
        if self._config.paused or not self._config.paired:
            return
        try:
            self._queue.put_nowait(toast)
        except queue.Full:
            log.warning("queue full, dropping notification")

    def _run(self) -> None:
        backoff = 1.0
        while True:
            toast = self._queue.get()
            while True:
                cfg = self._config
                if not cfg.paired:
                    break
                try:
                    code = self._client_factory(cfg.server_url).notify(cfg.pair_id, cfg.desktop_secret, toast)
                except httpx.HTTPError as exc:
                    code = None
                    self._on_status(f"Server unreachable, retrying ({type(exc).__name__})")
                if code == 202:
                    backoff = 1.0
                    self._on_status("Paired · forwarding")
                    break
                if code == 410:
                    self._on_unpaired()
                    break
                if code in (400, 401, 403, 409, 422):
                    log.warning("server rejected notification with %s; dropping", code)
                    break
                time.sleep(backoff)  # unreachable, 429 or 5xx
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
