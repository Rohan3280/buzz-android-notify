"""AE Buzz relay server: pairs a desktop agent with a phone and forwards notifications via FCM."""
from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from .db import Pairing, Store, secret_matches
from .fcm import FirebaseSender, Sender, TokenGone
from .firebase_config import load_app_options

PAIR_TOKEN_TTL_SECONDS = 10 * 60
RATE_LIMIT_PER_MINUTE = 60
MAX_TITLE_LENGTH = 200
# Keeps the FCM payload well under its 4 KB limit.
MAX_BODY_LENGTH = 1000


class CreatePairingResponse(BaseModel):
    pair_id: str
    desktop_secret: str
    pair_token: str
    expires_at: float
    public_url: str | None
    # Public Firebase settings for the phone (api_key, app_id, project_id, sender_id).
    firebase: dict[str, str] | None


class ClaimRequest(BaseModel):
    pair_token: str
    fcm_token: str = Field(min_length=1)


class ClaimResponse(BaseModel):
    phone_secret: str


class FcmTokenRequest(BaseModel):
    fcm_token: str = Field(min_length=1)


class NotifyRequest(BaseModel):
    title: str = Field(min_length=1)
    body: str | None = None
    app: str = "Buzz"
    ts: float | None = None


def _bearer(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return authorization.removeprefix("Bearer ").strip()


def create_app(
    store: Store | None = None,
    sender: Sender | None = None,
    public_url: str | None = None,
    firebase_options: dict[str, str] | None = None,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    store = store or Store(os.environ.get("AEBUZZ_DB", "aebuzz.db"))
    public_url = public_url if public_url is not None else os.environ.get("AEBUZZ_PUBLIC_URL")
    if firebase_options is None and os.environ.get("AEBUZZ_FIREBASE_APP_CONFIG"):
        # Fail at startup, not at pairing time, if the file is wrong.
        firebase_options = load_app_options(os.environ["AEBUZZ_FIREBASE_APP_CONFIG"])
    sender_holder: dict[str, Sender] = {}
    if sender is not None:
        sender_holder["s"] = sender
    recent_sends: dict[str, deque[float]] = defaultdict(deque)

    def get_sender() -> Sender:
        # Lazy so the server starts (and tests run) without Firebase credentials.
        if "s" not in sender_holder:
            sender_holder["s"] = FirebaseSender()
        return sender_holder["s"]

    def load(pair_id: str) -> Pairing:
        pairing = store.get(pair_id)
        if pairing is None:
            raise HTTPException(status.HTTP_410_GONE, "pairing no longer exists")
        return pairing

    app = FastAPI(title="AE Buzz relay")

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/pairings", response_model=CreatePairingResponse)
    def create_pairing() -> CreatePairingResponse:
        now = clock()
        store.delete_expired_unclaimed(now)
        pair_id = secrets.token_urlsafe(12)
        desktop_secret = secrets.token_urlsafe(32)
        pair_token = secrets.token_urlsafe(16)
        expires = now + PAIR_TOKEN_TTL_SECONDS
        store.create(pair_id, desktop_secret, pair_token, expires, now)
        return CreatePairingResponse(
            pair_id=pair_id,
            desktop_secret=desktop_secret,
            pair_token=pair_token,
            expires_at=expires,
            public_url=public_url,
            firebase=firebase_options,
        )

    @app.get("/pairings/{pair_id}")
    def pairing_status(pair_id: str, secret: str = Depends(_bearer)) -> dict:
        pairing = load(pair_id)
        if not (secret_matches(secret, pairing.desktop_secret_hash) or secret_matches(secret, pairing.phone_secret_hash)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "bad secret")
        return {"paired": pairing.claimed_at is not None, "phone_reachable": pairing.fcm_token is not None}

    @app.post("/pairings/{pair_id}/claim", response_model=ClaimResponse)
    def claim(pair_id: str, body: ClaimRequest) -> ClaimResponse:
        pairing = load(pair_id)
        if pairing.claimed_at is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "already paired")
        if not secret_matches(body.pair_token, pairing.pair_token_hash):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "bad pair token")
        if pairing.pair_token_expires is None or pairing.pair_token_expires < clock():
            raise HTTPException(status.HTTP_410_GONE, "pair token expired; show a new QR code")
        phone_secret = secrets.token_urlsafe(32)
        store.claim(pair_id, phone_secret, body.fcm_token, clock())
        return ClaimResponse(phone_secret=phone_secret)

    @app.put("/pairings/{pair_id}/fcm-token", status_code=status.HTTP_204_NO_CONTENT)
    def update_fcm_token(pair_id: str, body: FcmTokenRequest, secret: str = Depends(_bearer)) -> None:
        pairing = load(pair_id)
        if not secret_matches(secret, pairing.phone_secret_hash):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "bad phone secret")
        store.set_fcm_token(pair_id, body.fcm_token)

    @app.post("/pairings/{pair_id}/notify", status_code=status.HTTP_202_ACCEPTED)
    def notify(pair_id: str, body: NotifyRequest, secret: str = Depends(_bearer)) -> dict:
        pairing = load(pair_id)
        if not secret_matches(secret, pairing.desktop_secret_hash):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "bad desktop secret")
        if pairing.claimed_at is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "no phone paired yet")
        if pairing.fcm_token is None:
            raise HTTPException(status.HTTP_410_GONE, "phone is no longer registered; pair again")

        now = clock()
        window = recent_sends[pair_id]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= RATE_LIMIT_PER_MINUTE:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")
        window.append(now)

        try:
            message_body = body.body[:MAX_BODY_LENGTH] if body.body else None
            get_sender().send(pairing.fcm_token, body.title[:MAX_TITLE_LENGTH], message_body, body.app)
        except TokenGone:
            store.set_fcm_token(pair_id, None)
            raise HTTPException(status.HTTP_410_GONE, "phone is no longer registered; pair again")
        return {"sent": True}

    @app.delete("/pairings/{pair_id}", status_code=status.HTTP_204_NO_CONTENT)
    def unpair(pair_id: str, secret: str = Depends(_bearer)) -> None:
        pairing = store.get(pair_id)
        if pairing is None:
            return
        if not (secret_matches(secret, pairing.desktop_secret_hash) or secret_matches(secret, pairing.phone_secret_hash)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "bad secret")
        store.delete(pair_id)
        recent_sends.pop(pair_id, None)

    return app
