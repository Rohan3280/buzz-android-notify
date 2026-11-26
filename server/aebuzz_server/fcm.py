"""Firebase Cloud Messaging sender.

Credentials come from GOOGLE_APPLICATION_CREDENTIALS (path to the service-account
JSON), which firebase-admin reads on its own. The key file must never be committed.
"""
from __future__ import annotations

from typing import Protocol

# Must match the channel created in mobile/android/.../MainActivity.kt.
ANDROID_CHANNEL_ID = "buzz_messages_unison"


class TokenGone(Exception):
    """The phone's FCM token is no longer valid (app uninstalled or data cleared)."""


class Sender(Protocol):
    def send(self, fcm_token: str, title: str, body: str | None, app: str) -> None: ...


class FirebaseSender:
    def __init__(self) -> None:
        import firebase_admin

        if not firebase_admin._apps:
            firebase_admin.initialize_app()

    def warm_up(self) -> None:
        """Loads the messaging client and signs in to Google now, so the first send isn't slow."""
        import firebase_admin
        from firebase_admin import messaging  # noqa: F401  (the import itself takes seconds)

        firebase_admin.get_app().credential.get_access_token()

    def send(self, fcm_token: str, title: str, body: str | None, app: str) -> None:
        from firebase_admin import messaging

        message = messaging.Message(
            token=fcm_token,
            # With a body, Android's FCM builder uses BigTextStyle, so the alert expands to the full text.
            notification=messaging.Notification(title=title, body=body),
            data={"app": app},
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(channel_id=ANDROID_CHANNEL_ID, sound="unison"),
            ),
        )
        try:
            messaging.send(message)
        except (messaging.UnregisteredError, messaging.SenderIdMismatchError) as exc:
            raise TokenGone(str(exc)) from exc
