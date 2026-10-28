import json

import pytest
from fastapi.testclient import TestClient

from aebuzz_server.app import create_app
from aebuzz_server.db import Store
from aebuzz_server.firebase_config import FirebaseConfigError, load_app_options


def google_services(package="com.igrisstudios.aebuzz"):
    return {
        "project_info": {"project_number": "123456", "project_id": "my-proj"},
        "client": [
            {
                "client_info": {
                    "mobilesdk_app_id": "1:123456:android:abc",
                    "android_client_info": {"package_name": package},
                },
                "api_key": [{"current_key": "AIza-test"}],
            }
        ],
    }


def test_reads_options_for_our_package(tmp_path):
    path = tmp_path / "google-services.json"
    path.write_text(json.dumps(google_services()))
    assert load_app_options(path) == {
        "api_key": "AIza-test",
        "app_id": "1:123456:android:abc",
        "project_id": "my-proj",
        "sender_id": "123456",
    }


def test_rejects_file_for_another_app(tmp_path):
    path = tmp_path / "google-services.json"
    path.write_text(json.dumps(google_services("com.example.other")))
    with pytest.raises(FirebaseConfigError, match="no Android app"):
        load_app_options(path)


def test_rejects_unreadable_file(tmp_path):
    with pytest.raises(FirebaseConfigError):
        load_app_options(tmp_path / "missing.json")


def test_pairing_response_carries_firebase_options(tmp_path):
    options = {"api_key": "k", "app_id": "a", "project_id": "p", "sender_id": "s"}
    client = TestClient(create_app(Store(str(tmp_path / "t.db")), sender=object(), firebase_options=options))
    assert client.post("/pairings").json()["firebase"] == options
