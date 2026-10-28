"""SQLite storage for pairings. Secrets are stored as SHA-256 hashes only."""
from __future__ import annotations

import hashlib
import hmac
import sqlite3
import threading
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS pairings (
    id                  TEXT PRIMARY KEY,
    desktop_secret_hash TEXT NOT NULL,
    pair_token_hash     TEXT,
    pair_token_expires  REAL,
    phone_secret_hash   TEXT,
    fcm_token           TEXT,
    created_at          REAL NOT NULL,
    claimed_at          REAL
);
"""


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def secret_matches(secret: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    return hmac.compare_digest(hash_secret(secret), stored_hash)


@dataclass
class Pairing:
    id: str
    desktop_secret_hash: str
    pair_token_hash: str | None
    pair_token_expires: float | None
    phone_secret_hash: str | None
    fcm_token: str | None
    created_at: float
    claimed_at: float | None


class Store:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    def create(self, pairing_id: str, desktop_secret: str, pair_token: str, expires: float, now: float) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO pairings (id, desktop_secret_hash, pair_token_hash, pair_token_expires, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (pairing_id, hash_secret(desktop_secret), hash_secret(pair_token), expires, now),
            )

    def get(self, pairing_id: str) -> Pairing | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM pairings WHERE id = ?", (pairing_id,)).fetchone()
        return Pairing(**dict(row)) if row else None

    def claim(self, pairing_id: str, phone_secret: str, fcm_token: str, now: float) -> None:
        """Attach the phone and burn the one-time pair token."""
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE pairings SET phone_secret_hash = ?, fcm_token = ?, claimed_at = ?,"
                " pair_token_hash = NULL, pair_token_expires = NULL WHERE id = ?",
                (hash_secret(phone_secret), fcm_token, now, pairing_id),
            )

    def set_fcm_token(self, pairing_id: str, fcm_token: str | None) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE pairings SET fcm_token = ? WHERE id = ?", (fcm_token, pairing_id))

    def delete(self, pairing_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM pairings WHERE id = ?", (pairing_id,))

    def delete_expired_unclaimed(self, now: float) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM pairings WHERE claimed_at IS NULL AND pair_token_expires < ?", (now,)
            )
