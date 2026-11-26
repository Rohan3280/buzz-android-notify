"""BuzzFeed against a small fake Buzz server running on localhost."""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import struct
import time

import websockets
from coincurve import PublicKeyXOnly
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms

from aebuzz_desktop.buzz_feed import BuzzFeed, FeedState
from aebuzz_desktop.buzz_key import BuzzKeyMissing
from aebuzz_desktop.nostr import Keys, _hkdf_expand, _padded_len, conversation_key, event_id

ME_KEYS = Keys(bytes.fromhex("00" * 31 + "07"))
ME = ME_KEYS.pubkey
SAM = "bb" * 32
DANA = "cc" * 32
T0 = 1_800_000_000


def nip44_encrypt_to_self(plaintext: str) -> str:
    conv = conversation_key(ME_KEYS.secret, ME)
    nonce = os.urandom(32)
    keys = _hkdf_expand(conv, nonce, 76)
    raw = plaintext.encode()
    padded = struct.pack(">H", len(raw)) + raw + b"\x00" * (_padded_len(len(raw)) - len(raw))
    ct = Cipher(algorithms.ChaCha20(keys[:32], b"\x00" * 4 + keys[32:44]), mode=None).encryptor().update(padded)
    mac = hmac.new(keys[44:], nonce + ct, hashlib.sha256).digest()
    return base64.b64encode(b"\x02" + nonce + ct + mac).decode()


_n = 0


def event(kind, pubkey, tags, content="", created_at=T0 + 10):
    global _n
    _n += 1
    return {"id": f"{_n:064x}", "pubkey": pubkey, "kind": kind, "tags": tags, "content": content,
            "created_at": created_at}


def channel_meta(cid, name, ctype):
    return event(39000, "ff" * 32, [["d", cid], ["name", name], ["t", ctype]], created_at=T0 - 100)


def membership(cid):
    return event(39002, "ff" * 32, [["d", cid], ["p", ME]], created_at=T0 - 100)


def profile(pubkey, name):
    return event(0, pubkey, [], json.dumps({"display_name": name}), created_at=T0 - 100)


class FakeBuzz:
    def __init__(self):
        self.channels = {"ch-1": ("backend", "stream"), "ch-att": ("Attendance", "stream")}
        self.stored = [profile(SAM, "Sam"), profile(DANA, "Dana Lee")]
        self.auth_events = []
        self.msg_reqs = []
        self.live = {}  # sub -> websocket
        self.subscribed = asyncio.Event()

    def matches(self, flt):
        kinds = flt.get("kinds")
        if kinds == [39002]:
            return [membership(cid) for cid in self.channels]
        if kinds == [39000]:
            return [channel_meta(cid, *self.channels[cid]) for cid in flt["#d"] if cid in self.channels]
        out = []
        for e in self.stored:
            if kinds and e["kind"] not in kinds:
                continue
            if "authors" in flt and e["pubkey"] not in flt["authors"]:
                continue
            if "#h" in flt and not any(t[0] == "h" and t[1] in flt["#h"] for t in e["tags"]):
                continue
            if "#d" in flt and not any(t[0] == "d" and t[1] in flt["#d"] for t in e["tags"]):
                continue
            if e["created_at"] < flt.get("since", 0):
                continue
            out.append(e)
        return out

    async def handler(self, ws):
        await ws.send(json.dumps(["AUTH", "challenge-1"]))
        async for raw in ws:
            msg = json.loads(raw)
            if msg[0] == "AUTH":
                self.auth_events.append(msg[1])
                await ws.send(json.dumps(["OK", msg[1]["id"], True, ""]))
            elif msg[0] == "REQ":
                sub, flt = msg[1], msg[2]
                if sub == "msgs":
                    self.msg_reqs.append(flt)
                for e in self.matches(flt):
                    await ws.send(json.dumps(["EVENT", sub, e]))
                await ws.send(json.dumps(["EOSE", sub]))
                if not sub.startswith("q"):
                    self.live[sub] = ws
                if sub == "msgs":
                    self.subscribed.set()

    async def push(self, sub, e):
        self.stored.append(e)
        await self.live[sub].send(json.dumps(["EVENT", sub, e]))


async def wait_for(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > end:
            raise AssertionError("timed out")
        await asyncio.sleep(0.02)


def run_with_feed(scenario, *, key_loader=lambda: ME_KEYS, url_from_server=True):
    async def main():
        fake = FakeBuzz()
        async with websockets.serve(fake.handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            url = f"ws://127.0.0.1:{port}" if url_from_server else None
            alerts, states = [], []
            feed = BuzzFeed(lambda: url, alerts.append, states.append, key_loader=key_loader,
                            clock=lambda: T0)
            task = asyncio.create_task(feed._main())
            try:
                await scenario(fake, feed, alerts, states, task)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(main())


def test_signs_in_and_forwards_new_channel_message():
    async def scenario(fake, feed, alerts, states, task):
        await asyncio.wait_for(fake.subscribed.wait(), 5)
        auth = fake.auth_events[0]
        assert ["challenge", "challenge-1"] in auth["tags"]
        assert auth["id"] == event_id(auth["pubkey"], auth["created_at"], 22242, auth["tags"], "")
        assert PublicKeyXOnly(bytes.fromhex(ME)).verify(bytes.fromhex(auth["sig"]), bytes.fromhex(auth["id"]))
        assert sorted(fake.msg_reqs[0]["#h"]) == ["ch-1", "ch-att"]

        await fake.push("msgs", event(9, SAM, [["h", "ch-1"]], "deploy failed"))
        await wait_for(lambda: alerts)
        assert alerts[0].title == "Sam in #backend"
        assert alerts[0].body == "deploy failed"
        assert FeedState.CONNECTED in states

    run_with_feed(scenario)


def test_skips_own_messages_and_backlog_from_before_start():
    async def scenario(fake, feed, alerts, states, task):
        await asyncio.wait_for(fake.subscribed.wait(), 5)
        await fake.push("msgs", event(9, SAM, [["h", "ch-1"]], "old", created_at=T0 - 30))
        await fake.push("msgs", event(9, ME, [["h", "ch-1"]], "mine"))
        await fake.push("msgs", event(9, SAM, [["h", "ch-1"]], "new"))
        await wait_for(lambda: alerts)
        await asyncio.sleep(0.2)
        assert [a.body for a in alerts] == ["new"]

    run_with_feed(scenario)


def test_muted_channel_skipped_unless_mentioned():
    async def scenario(fake, feed, alerts, states, task):
        await asyncio.wait_for(fake.subscribed.wait(), 5)
        store = {"version": 1, "channels": {"ch-att": {"muted": True, "updatedAt": 1}}}
        mutes = event(30078, ME, [["d", "channel-mutes"]], nip44_encrypt_to_self(json.dumps(store)))
        await fake.push("mutes", mutes)
        await asyncio.sleep(0.2)
        await fake.push("msgs", event(9, SAM, [["h", "ch-att"]], "clocked in"))
        await fake.push("msgs", event(9, SAM, [["h", "ch-att"], ["p", ME]], "@Alex too"))
        await wait_for(lambda: alerts)
        await asyncio.sleep(0.2)
        assert [a.body for a in alerts] == ["@Alex too"]
        assert alerts[0].title == "Sam mentioned you in #Attendance"

    run_with_feed(scenario)


def test_new_dm_first_message_is_forwarded():
    async def scenario(fake, feed, alerts, states, task):
        await asyncio.wait_for(fake.subscribed.wait(), 5)
        fake.subscribed.clear()
        # Dana opens a brand-new DM: the first message lands, then we hear we were added.
        fake.channels["dm-new"] = ("", "dm")
        fake.stored.append(event(9, DANA, [["h", "dm-new"]], "Hi there, let me know"))
        await fake.push("joins", event(44100, "ff" * 32, [["h", "dm-new"], ["p", ME]]))
        await asyncio.wait_for(fake.subscribed.wait(), 5)
        await wait_for(lambda: alerts)
        assert alerts[0].title == "Dana Lee"
        assert alerts[0].body == "Hi there, let me know"
        assert "dm-new" in fake.msg_reqs[-1]["#h"]

    run_with_feed(scenario)


def test_reconnects_and_catches_up_without_repeats():
    async def scenario(fake, feed, alerts, states, task):
        await asyncio.wait_for(fake.subscribed.wait(), 5)
        await fake.push("msgs", event(9, SAM, [["h", "ch-1"]], "before drop", created_at=T0 + 5))
        await wait_for(lambda: len(alerts) == 1)
        fake.subscribed.clear()
        # Missed while disconnected:
        fake.stored.append(event(9, SAM, [["h", "ch-1"]], "while away", created_at=T0 + 6))
        await fake.live["msgs"].close()
        await asyncio.wait_for(fake.subscribed.wait(), 10)
        await wait_for(lambda: len(alerts) == 2, timeout=10)
        await asyncio.sleep(0.2)
        assert [a.body for a in alerts] == ["before drop", "while away"]
        assert FeedState.UNREACHABLE in states
        assert fake.msg_reqs[-1]["since"] <= T0 + 5

    run_with_feed(scenario)


def test_missing_key_reports_no_key():
    def no_key():
        raise BuzzKeyMissing("none")

    async def scenario(fake, feed, alerts, states, task):
        await asyncio.wait_for(task, 5)
        assert states == [FeedState.NO_KEY]
        assert not fake.auth_events

    run_with_feed(scenario, key_loader=no_key)


def test_missing_address_reports_no_address():
    async def scenario(fake, feed, alerts, states, task):
        await asyncio.wait_for(task, 5)
        assert states == [FeedState.NO_ADDRESS]

    run_with_feed(scenario, url_from_server=False)
