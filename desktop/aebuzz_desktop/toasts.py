"""Pure logic for picking new Buzz toasts out of the Windows notification list.

Kept free of winrt imports so it can be unit-tested anywhere.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Hashable, Iterable

# Windows app IDs of the Buzz desktop apps whose notifications are forwarded:
# the original Buzz app and the newer Buzz Foundation build.
BUZZ_AUMIDS = ("xyz.block.buzz.app", "xyz.block.buzz.desktop")

# Both apps can be open at once and show the same message, a moment apart.
DUPLICATE_WINDOW_SECONDS = 10


@dataclass(frozen=True)
class Toast:
    title: str
    body: str | None
    app: str | None = None  # app ID that showed it


def parse_toast(texts: Iterable[str], app: str | None = None) -> Toast | None:
    """Buzz toasts carry [title, (whitespace filler,) body]; blank lines are dropped."""
    lines = [t.strip() for t in texts if t and t.strip()]
    if not lines:
        return None
    return Toast(title=lines[0], body="\n".join(lines[1:]) or None, app=app)


class NewToastTracker:
    """Reports each toast once, ignoring whatever was already on screen at startup."""

    def __init__(self) -> None:
        self._seen: set[Hashable] | None = None

    def update(self, current: Iterable[tuple[Hashable, Toast | None]]) -> list[Toast]:
        current = list(current)
        ids = {toast_id for toast_id, _ in current}
        if self._seen is None:
            self._seen = ids
            return []
        new = [toast for toast_id, toast in current if toast_id not in self._seen and toast]
        # Only keep IDs still in Action Center so the set can't grow without bound.
        self._seen = ids
        return new


class CrossAppDuplicateFilter:
    """Drops a toast when the *other* Buzz app just showed the same message.

    The two apps title the same message differently, so only the message text is
    compared. Repeats within one app (two people both saying "ok") still go through.
    """

    def __init__(self, window: float = DUPLICATE_WINDOW_SECONDS, clock=time.monotonic) -> None:
        self._window = window
        self._clock = clock
        self._recent: dict[str, tuple[str | None, float]] = {}

    def allow(self, toast: Toast) -> bool:
        now = self._clock()
        self._recent = {k: v for k, v in self._recent.items() if now - v[1] <= self._window}
        key = (toast.body or toast.title).strip()
        seen = self._recent.get(key)
        if seen and seen[0] != toast.app:
            return False
        self._recent[key] = (toast.app, now)
        return True
