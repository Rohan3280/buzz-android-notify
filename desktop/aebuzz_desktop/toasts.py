"""Pure logic for picking new Buzz toasts out of the Windows notification list.

Kept free of winrt imports so it can be unit-tested anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

BUZZ_AUMID = "xyz.block.buzz.app"


@dataclass(frozen=True)
class Toast:
    title: str
    body: str | None


def parse_toast(texts: Iterable[str]) -> Toast | None:
    """Buzz toasts carry [title, whitespace filler, body]; blank lines are dropped."""
    lines = [t.strip() for t in texts if t and t.strip()]
    if not lines:
        return None
    return Toast(title=lines[0], body="\n".join(lines[1:]) or None)


class NewToastTracker:
    """Reports each toast once, ignoring whatever was already on screen at startup."""

    def __init__(self) -> None:
        self._seen: set[int] | None = None

    def update(self, current: Iterable[tuple[int, Toast | None]]) -> list[Toast]:
        current = list(current)
        ids = {toast_id for toast_id, _ in current}
        if self._seen is None:
            self._seen = ids
            return []
        new = [toast for toast_id, toast in current if toast_id not in self._seen and toast]
        # Only keep IDs still in Action Center so the set can't grow without bound.
        self._seen = ids
        return new
