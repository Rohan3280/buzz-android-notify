"""Polls Windows' UserNotificationListener for new Buzz toasts.

Polling (not the NotificationChanged event) because the event needs package
identity, which a plain Python process doesn't have.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

from winrt.windows.ui.notifications import KnownNotificationBindings, NotificationKinds
from winrt.windows.ui.notifications.management import (
    UserNotificationListener,
    UserNotificationListenerAccessStatus,
)

from .toasts import BUZZ_AUMID, NewToastTracker, Toast, parse_toast

log = logging.getLogger(__name__)

POLL_SECONDS = 0.5


class AccessDenied(Exception):
    pass


def _content_of(notification) -> Toast | None:
    binding = notification.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
    if binding is None:
        return None
    return parse_toast(t.text for t in binding.get_text_elements())


async def _buzz_toasts(listener) -> list[tuple[int, Toast | None]]:
    toasts = []
    for n in await listener.get_notifications_async(NotificationKinds.TOAST):
        try:
            if n.app_info.app_user_model_id != BUZZ_AUMID:
                continue
            toasts.append((n.id, _content_of(n)))
        except Exception:  # a single malformed toast must not stop the watcher
            log.exception("could not read toast")
    return toasts


class BuzzToastWatcher:
    """Calls on_toast(toast) from a background thread for every new Buzz toast."""

    def __init__(self, on_toast: Callable[[Toast], None], on_error: Callable[[str], None]) -> None:
        self._on_toast = on_toast
        self._on_error = on_error
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="buzz-toast-watcher", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            asyncio.run(self._loop())
        except AccessDenied as exc:
            self._on_error(str(exc))
        except Exception as exc:
            log.exception("watcher crashed")
            self._on_error(f"Notification watcher stopped: {exc}")

    async def _loop(self) -> None:
        listener = UserNotificationListener.current
        status = await listener.request_access_async()
        if status != UserNotificationListenerAccessStatus.ALLOWED:
            raise AccessDenied(
                "Windows blocked notification access. Turn on Settings > Privacy & security > "
                "Notifications > 'Let apps access your notifications'."
            )
        tracker = NewToastTracker()
        while not self._stop.is_set():
            try:
                for toast in tracker.update(await _buzz_toasts(listener)):
                    self._on_toast(toast)
            except Exception:
                log.exception("poll failed")
            await asyncio.sleep(POLL_SECONDS)
