"""Pure rules: which Buzz events reach the phone, and how they're worded.

Kept free of networking so it can be unit-tested anywhere. Wording follows the
Buzz desktop app's own notifications.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

STREAM_MESSAGE = 9
STREAM_MESSAGE_V2 = 40002  # Buzz's rich-content message
FORUM_POST = 45001
FORUM_COMMENT = 45003
HUDDLE_STARTED = 48100  # only alerted in DMs, like Buzz

MESSAGE_KINDS = (STREAM_MESSAGE, STREAM_MESSAGE_V2, FORUM_POST, FORUM_COMMENT)
SUBSCRIBED_KINDS = (*MESSAGE_KINDS, HUDDLE_STARTED)


@dataclass(frozen=True)
class Alert:
    title: str
    body: str | None


@dataclass(frozen=True)
class Channel:
    id: str
    name: str
    type: str  # "stream", "forum", "dm" or "workflow"

    @property
    def is_dm(self) -> bool:
        return self.type == "dm"


def _tags(event: dict, name: str) -> list[list[str]]:
    return [t for t in event.get("tags", []) if len(t) > 1 and t[0] == name]


def channel_id(event: dict) -> str | None:
    tags = _tags(event, "h")
    return tags[0][1] if tags else None


def is_broadcast(event: dict) -> bool:
    return any(t[1] == "1" for t in _tags(event, "broadcast"))


def is_thread_reply(event: dict) -> bool:
    return not is_broadcast(event) and any(
        len(t) > 3 and t[3] == "reply" for t in _tags(event, "e")
    )


def mentions(event: dict, me: str) -> bool:
    """A p-tag naming me. A workflow's ["p", owner, "", "owner"] tag is attribution, not a mention."""
    workflow = any(t[1] == "true" for t in _tags(event, "buzz:workflow"))
    return any(
        t[1].lower() == me and not (workflow and len(t) > 3 and t[3] == "owner")
        for t in _tags(event, "p")
    )


def should_forward(event: dict, me: str, channel: Channel | None, muted: set[str]) -> bool:
    if event.get("pubkey", "").lower() == me:
        return False
    kind = event.get("kind")
    if kind == HUDDLE_STARTED:
        return channel is not None and channel.is_dm
    if kind not in MESSAGE_KINDS:
        return False
    if channel_id(event) in muted and not (mentions(event, me) or is_broadcast(event)):
        return False
    return True


def format_alert(event: dict, me: str, channel: Channel | None, sender: str | None) -> Alert:
    text = (event.get("content") or "").strip()
    if channel is not None and channel.is_dm:
        title = sender or channel.name.strip() or "Direct message"
        if event.get("kind") == HUDDLE_STARTED:
            return Alert(title, "Started a huddle")
        return Alert(title, text or "New message")

    where = f" in #{channel.name.strip()}" if channel is not None and channel.name.strip() else ""
    kind = event.get("kind")
    if mentions(event, me):
        prefix = f"{sender} mentioned you" if sender else "@Mention"
    elif kind == FORUM_POST:
        prefix = f"{sender} posted" if sender else "New post"
    elif kind == FORUM_COMMENT:
        prefix = f"{sender} commented" if sender else "New comment"
    elif is_thread_reply(event):
        prefix = f"{sender} replied" if sender else "Reply"
    else:
        prefix = sender or "New message"
    return Alert(prefix + where, text or None)


def display_name(profile_event: dict | None) -> str | None:
    """Buzz's order: display_name, then name, then nip05."""
    if not profile_event:
        return None
    try:
        meta = json.loads(profile_event.get("content") or "{}")
    except ValueError:
        return None
    if not isinstance(meta, dict):
        return None
    for key in ("display_name", "name", "nip05"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
