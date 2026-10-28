"""Public Firebase settings the phone app needs, read from the project's google-services.json.

These values aren't secret (they ship inside every Firebase Android app); they're
handed to the phone in the pairing QR so one prebuilt APK works with anyone's
Firebase project.
"""
from __future__ import annotations

import json
from pathlib import Path

ANDROID_PACKAGE = "com.igrisstudios.aebuzz"


class FirebaseConfigError(Exception):
    pass


def load_app_options(path: str | Path) -> dict[str, str]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FirebaseConfigError(f"Can't read google-services.json at {path}: {exc}") from exc
    for client in data.get("client", []):
        info = client.get("client_info", {})
        if info.get("android_client_info", {}).get("package_name") == ANDROID_PACKAGE:
            return {
                "api_key": client["api_key"][0]["current_key"],
                "app_id": info["mobilesdk_app_id"],
                "project_id": data["project_info"]["project_id"],
                "sender_id": data["project_info"]["project_number"],
            }
    raise FirebaseConfigError(
        f"google-services.json has no Android app with package {ANDROID_PACKAGE}; "
        "add one in the Firebase console and download the file again."
    )
