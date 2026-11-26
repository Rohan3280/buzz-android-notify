"""Reads new Buzz messages straight from the Buzz server and hands each one on as an Alert.

Signs in as the user (NIP-42) with the key the Buzz desktop app saved, follows
every channel and DM the user belongs to, and keeps up with new memberships
(e.g. a brand-new DM) and the user's mute list. Runs in its own thread.
"""
from __future__ import annotations

import asyncio
import contextlib
import enum
import itertools
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Callable

import websockets

from .buzz_key import BuzzKeyMissing, load_buzz_keys
from .messages import (
    SUBSCRIBED_KINDS,
    Alert,
    Channel,
    channel_id,
    display_name,
    format_alert,
    should_forward,
)
from .nostr import Keys, auth_event, nip44_decrypt_from_self

log = logging.getLogger(__name__)

CHANNEL_MEMBERS_KIND = 39002
CHANNEL_META_KIND = 39000
MEMBERSHIP_CHANGE_KINDS = (44100, 44101)
APP_DATA_KIND = 30078
MUTES_D_TAG = "channel-mutes"
PROFILE_KIND = 0

QUERY_TIMEOUT = 20
CATCH_UP_MARGIN = 60  # seconds re-read after a reconnect, in case clocks differ
NEW_CHANNEL_LOOKBACK = 300  # a new DM's first message can land just before we hear we joined
CHANNEL_REFRESH_SECONDS = 600
MAX_BACKOFF = 300
SEEN_LIMIT = 5000
MAX_MESSAGE_BYTES = 8 * 1024 * 1024


class FeedState(enum.Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    UNREACHABLE = "unreachable"
    NO_KEY = "no_key"
    NO_ADDRESS = "no_address"


class RelayError(Exception):
    pass


def _tag(event: dict, name: str) -> str | None:
    return next((t[1] for t in event.get("tags", []) if len(t) > 1 and t[0] == name), None)


def parse_channel(event: dict) -> Channel | None:
    cid = _tag(event, "d")
    if not cid:
        return None
    ctype = _tag(event, "t") or "stream"  # the first t tag is the channel type
    return Channel(cid, _tag(event, "name") or "", ctype)


def parse_mutes(plaintext: str) -> set[str]:
    store = json.loads(plaintext)
    channels = store.get("channels") if isinstance(store, dict) else None
    if not isinstance(channels, dict):
        return set()
    return {cid for cid, entry in channels.items() if isinstance(entry, dict) and entry.get("muted") is True}


class _Connection:
    """One signed-in WebSocket: request/response queries plus live subscriptions."""

    def __init__(self, ws) -> None:
        self._ws = ws
        self._ids = itertools.count(1)
        self._queries: dict[str, tuple[list, asyncio.Future]] = {}
        self._live: dict[str, Callable[[dict], None]] = {}

    async def _send(self, msg: list) -> None:
        await self._ws.send(json.dumps(msg, separators=(",", ":")))

    async def authenticate(self, keys: Keys, relay_url: str) -> None:
        challenge = json.loads(await asyncio.wait_for(self._ws.recv(), QUERY_TIMEOUT))
        if not (isinstance(challenge, list) and challenge[:1] == ["AUTH"] and len(challenge) > 1):
            raise RelayError("server did not ask to sign in")
        event = auth_event(keys, relay_url, challenge[1])
        await self._send(["AUTH", event])
        while True:
            reply = json.loads(await asyncio.wait_for(self._ws.recv(), QUERY_TIMEOUT))
            if isinstance(reply, list) and reply[:2] == ["OK", event["id"]]:
                if reply[2] is not True:
                    raise RelayError(f"sign-in refused: {reply[3] if len(reply) > 3 else ''}")
                return

    async def read_forever(self) -> None:
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(msg, list) or len(msg) < 2:
                continue
            kind, sub = msg[0], msg[1]
            if kind == "EVENT" and len(msg) > 2 and isinstance(msg[2], dict):
                if sub in self._queries:
                    self._queries[sub][0].append(msg[2])
                elif sub in self._live:
                    self._live[sub](msg[2])
            elif kind == "EOSE":
                pending = self._queries.get(sub)
                if pending and not pending[1].done():
                    pending[1].set_result(None)
            elif kind == "CLOSED":
                reason = msg[2] if len(msg) > 2 else ""
                pending = self._queries.get(sub)
                if pending and not pending[1].done():
                    pending[1].set_exception(RelayError(f"query closed: {reason}"))
                elif sub in self._live:
                    log.warning("server closed subscription %s: %s", sub, reason)
            elif kind == "NOTICE":
                log.info("server notice: %s", sub)

    async def query(self, flt: dict) -> list[dict]:
        sub = f"q{next(self._ids)}"
        done = asyncio.get_running_loop().create_future()
        events: list[dict] = []
        self._queries[sub] = (events, done)
        try:
            await self._send(["REQ", sub, flt])
            await asyncio.wait_for(done, QUERY_TIMEOUT)
        finally:
            self._queries.pop(sub, None)
            with contextlib.suppress(Exception):
                await self._send(["CLOSE", sub])
        return events

    async def subscribe(self, sub: str, flt: dict, on_event: Callable[[dict], None]) -> None:
        """(Re)opens a live subscription; reusing a name replaces its filter."""
        self._live[sub] = on_event
        await self._send(["REQ", sub, flt])


class BuzzFeed:
    """Calls on_alert(alert) from a background thread for every new Buzz message worth forwarding."""

    def __init__(
        self,
        relay_url: Callable[[], str | None],
        on_alert: Callable[[Alert], None],
        on_state: Callable[[FeedState], None],
        key_loader: Callable[[], Keys] = load_buzz_keys,
        connect=websockets.connect,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._relay_url = relay_url
        self._on_alert = on_alert
        self._on_state = on_state
        self._key_loader = key_loader
        self._connect = connect
        self._clock = clock
        self._stop = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._thread = threading.Thread(target=self._run, name="buzz-feed", daemon=True)
        # Only messages sent after AE Buzz started are forwarded.
        self._started_at = int(clock())
        self._since = self._started_at  # newest message time seen; reconnects catch up from here
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._connected = False  # whether the current session got as far as following channels

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._loop and self._task:
            self._loop.call_soon_threadsafe(self._task.cancel)

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Buzz feed crashed")
            self._on_state(FeedState.UNREACHABLE)

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.current_task()
        try:
            keys = self._key_loader()
        except BuzzKeyMissing:
            log.error("no Buzz key found in Windows Credential Manager")
            self._on_state(FeedState.NO_KEY)
            return
        url = self._relay_url()
        if not url:
            log.error("no Buzz server address found")
            self._on_state(FeedState.NO_ADDRESS)
            return
        log.info("reading Buzz messages from %s", url)
        backoff = 1.0
        while not self._stop.is_set():
            self._on_state(FeedState.CONNECTING)
            self._connected = False
            try:
                await self._session(keys, url)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # network drops, sign-in refusals, server surprises
                log.warning("Buzz connection ended: %s: %s", type(exc).__name__, exc)
            if self._stop.is_set():
                return
            if self._connected:
                backoff = 1.0
            self._on_state(FeedState.UNREACHABLE)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

    async def _session(self, keys: Keys, url: str) -> None:
        me = keys.pubkey
        async with self._connect(url, max_size=MAX_MESSAGE_BYTES, open_timeout=QUERY_TIMEOUT) as ws:
            conn = _Connection(ws)
            await conn.authenticate(keys, url)
            reader = asyncio.create_task(conn.read_forever())
            worker = asyncio.create_task(self._work(conn, keys, me))
            try:
                done, _ = await asyncio.wait({reader, worker}, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()  # re-raise whatever ended the session
                raise RelayError("connection closed")
            finally:
                for task in (reader, worker):
                    task.cancel()
                    with contextlib.suppress(BaseException):
                        await task

    async def _work(self, conn: _Connection, keys: Keys, me: str) -> None:
        inbox: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        channels = await self._load_channels(conn, me)
        muted: set[str] = set()
        mutes_at = -1
        names: dict[str, str | None] = {}

        await conn.subscribe(
            "mutes",
            {"kinds": [APP_DATA_KIND], "authors": [me], "#d": [MUTES_D_TAG], "limit": 1},
            lambda e: inbox.put_nowait(("mutes", e)),
        )
        await conn.subscribe(
            "joins",
            {"kinds": list(MEMBERSHIP_CHANGE_KINDS), "#p": [me], "since": int(self._clock())},
            lambda e: inbox.put_nowait(("joins", e)),
        )
        await self._subscribe_messages(conn, channels, self._since - CATCH_UP_MARGIN, inbox)
        self._connected = True
        self._on_state(FeedState.CONNECTED)
        log.info("following %d channels", len(channels))

        refresh_at = time.monotonic() + CHANNEL_REFRESH_SECONDS
        while True:
            try:
                source, event = await asyncio.wait_for(
                    inbox.get(), max(1.0, refresh_at - time.monotonic())
                )
            except asyncio.TimeoutError:
                source, event = "refresh", {}

            if source == "msg":
                await self._handle_message(conn, event, me, channels, muted, names)
            elif source == "mutes":
                if event.get("created_at", 0) > mutes_at:
                    try:
                        muted = parse_mutes(nip44_decrypt_from_self(keys, event.get("content", "")))
                        mutes_at = event.get("created_at", 0)
                        log.info("mute list: %d muted channels", len(muted))
                    except (ValueError, TypeError):
                        log.warning("could not read the mute list; keeping the previous one")
            else:  # "joins" or the periodic refresh
                fresh = await self._load_channels(conn, me)
                if fresh.keys() != channels.keys():
                    log.info("channel list changed: %d -> %d", len(channels), len(fresh))
                    since = int(self._clock()) - NEW_CHANNEL_LOOKBACK
                    await self._subscribe_messages(conn, fresh, since, inbox)
                channels = fresh
                refresh_at = time.monotonic() + CHANNEL_REFRESH_SECONDS

    async def _subscribe_messages(self, conn, channels: dict[str, Channel], since: int, inbox) -> None:
        if not channels:
            return
        await conn.subscribe(
            "msgs",
            {"kinds": list(SUBSCRIBED_KINDS), "#h": sorted(channels), "since": since},
            lambda e: inbox.put_nowait(("msg", e)),
        )

    async def _load_channels(self, conn: _Connection, me: str) -> dict[str, Channel]:
        memberships = await conn.query({"kinds": [CHANNEL_MEMBERS_KIND], "#p": [me], "limit": 1000})
        ids = sorted({cid for e in memberships if (cid := _tag(e, "d"))})
        latest: dict[str, tuple[int, Channel]] = {}
        for i in range(0, len(ids), 200):
            chunk = ids[i : i + 200]
            for e in await conn.query({"kinds": [CHANNEL_META_KIND], "#d": chunk, "limit": 1000}):
                ch = parse_channel(e)
                if ch and ch.id in chunk and e.get("created_at", 0) >= latest.get(ch.id, (-1,))[0]:
                    latest[ch.id] = (e.get("created_at", 0), ch)
        channels = {cid: latest[cid][1] if cid in latest else Channel(cid, "", "stream") for cid in ids}
        # Buzz hides "system" channels; they aren't conversations.
        return {cid: ch for cid, ch in channels.items() if ch.type != "system"}

    async def _handle_message(self, conn, event, me, channels, muted, names) -> None:
        eid = event.get("id")
        if not isinstance(eid, str) or eid in self._seen:
            return
        self._seen[eid] = None
        if len(self._seen) > SEEN_LIMIT:
            self._seen.popitem(last=False)
        created = event.get("created_at", 0)
        self._since = max(self._since, min(created, int(self._clock())))
        if created < self._started_at:
            return  # sent before AE Buzz started
        channel = channels.get(channel_id(event) or "")
        if not should_forward(event, me, channel, muted):
            return
        sender = await self._sender_name(conn, event.get("pubkey", ""), names)
        self._on_alert(format_alert(event, me, channel, sender))

    async def _sender_name(self, conn, pubkey: str, names: dict[str, str | None]) -> str | None:
        if pubkey not in names:
            try:
                found = await conn.query({"kinds": [PROFILE_KIND], "authors": [pubkey], "limit": 1})
            except (RelayError, asyncio.TimeoutError):
                return None  # try again next time
            names[pubkey] = display_name(max(found, key=lambda e: e.get("created_at", 0), default=None))
        return names[pubkey]
