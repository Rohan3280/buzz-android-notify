import pytest
from fastapi.testclient import TestClient

from aebuzz_server.app import PAIR_TOKEN_TTL_SECONDS, RATE_LIMIT_PER_MINUTE, create_app
from aebuzz_server.db import Store
from aebuzz_server.fcm import TokenGone


class FakeSender:
    def __init__(self):
        self.sent = []
        self.gone = False

    def send(self, fcm_token, title, body, app):
        if self.gone:
            raise TokenGone("unregistered")
        self.sent.append((fcm_token, title, body, app))


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def env(tmp_path):
    sender, clock = FakeSender(), Clock()
    app = create_app(Store(str(tmp_path / "t.db")), sender, public_url="https://relay.test", clock=clock)
    return TestClient(app), sender, clock


def auth(secret):
    return {"Authorization": f"Bearer {secret}"}


def paired(client):
    p = client.post("/pairings").json()
    phone = client.post(f"/pairings/{p['pair_id']}/claim", json={"pair_token": p["pair_token"], "fcm_token": "tok-1"})
    assert phone.status_code == 200
    return p, phone.json()["phone_secret"]


def test_create_returns_public_url_and_secrets(env):
    client, _, _ = env
    body = client.post("/pairings").json()
    assert body["public_url"] == "https://relay.test"
    assert body["pair_id"] and body["desktop_secret"] and body["pair_token"]


def test_full_flow_sends_title_and_body(env):
    client, sender, _ = env
    p, _ = paired(client)
    r = client.post(
        f"/pairings/{p['pair_id']}/notify",
        json={"title": "Sooraj in #backend", "body": "deploy failed"},
        headers=auth(p["desktop_secret"]),
    )
    assert r.status_code == 202
    assert sender.sent == [("tok-1", "Sooraj in #backend", "deploy failed", "Buzz")]


def test_body_is_optional(env):
    client, sender, _ = env
    p, _ = paired(client)
    client.post(f"/pairings/{p['pair_id']}/notify", json={"title": "Sooraj"}, headers=auth(p["desktop_secret"]))
    assert sender.sent == [("tok-1", "Sooraj", None, "Buzz")]


def test_notify_before_claim_is_conflict(env):
    client, _, _ = env
    p = client.post("/pairings").json()
    r = client.post(f"/pairings/{p['pair_id']}/notify", json={"title": "x"}, headers=auth(p["desktop_secret"]))
    assert r.status_code == 409


def test_pair_token_is_single_use(env):
    client, _, _ = env
    p, _ = paired(client)
    r = client.post(f"/pairings/{p['pair_id']}/claim", json={"pair_token": p["pair_token"], "fcm_token": "tok-2"})
    assert r.status_code == 409


def test_expired_pair_token_rejected(env):
    client, _, clock = env
    p = client.post("/pairings").json()
    clock.now += PAIR_TOKEN_TTL_SECONDS + 1
    r = client.post(f"/pairings/{p['pair_id']}/claim", json={"pair_token": p["pair_token"], "fcm_token": "t"})
    assert r.status_code == 410


def test_wrong_pair_token_rejected(env):
    client, _, _ = env
    p = client.post("/pairings").json()
    r = client.post(f"/pairings/{p['pair_id']}/claim", json={"pair_token": "nope", "fcm_token": "t"})
    assert r.status_code == 403


def test_bad_or_missing_secret(env):
    client, sender, _ = env
    p, phone_secret = paired(client)
    url = f"/pairings/{p['pair_id']}/notify"
    assert client.post(url, json={"title": "x"}).status_code == 401
    assert client.post(url, json={"title": "x"}, headers=auth("wrong")).status_code == 403
    # The phone secret must not be usable to send notifications.
    assert client.post(url, json={"title": "x"}, headers=auth(phone_secret)).status_code == 403
    assert sender.sent == []


def test_phone_can_refresh_fcm_token(env):
    client, sender, _ = env
    p, phone_secret = paired(client)
    r = client.put(f"/pairings/{p['pair_id']}/fcm-token", json={"fcm_token": "tok-new"}, headers=auth(phone_secret))
    assert r.status_code == 204
    client.post(f"/pairings/{p['pair_id']}/notify", json={"title": "x"}, headers=auth(p["desktop_secret"]))
    assert sender.sent[-1][0] == "tok-new"


def test_rate_limit(env):
    client, _, clock = env
    p, _ = paired(client)
    url = f"/pairings/{p['pair_id']}/notify"
    for _ in range(RATE_LIMIT_PER_MINUTE):
        assert client.post(url, json={"title": "x"}, headers=auth(p["desktop_secret"])).status_code == 202
    assert client.post(url, json={"title": "x"}, headers=auth(p["desktop_secret"])).status_code == 429
    clock.now += 61
    assert client.post(url, json={"title": "x"}, headers=auth(p["desktop_secret"])).status_code == 202


def test_unpair_from_phone_then_notify_is_gone(env):
    client, _, _ = env
    p, phone_secret = paired(client)
    assert client.delete(f"/pairings/{p['pair_id']}", headers=auth(phone_secret)).status_code == 204
    r = client.post(f"/pairings/{p['pair_id']}/notify", json={"title": "x"}, headers=auth(p["desktop_secret"]))
    assert r.status_code == 410


def test_unregistered_phone_marks_pairing_gone(env):
    client, sender, _ = env
    p, _ = paired(client)
    sender.gone = True
    url = f"/pairings/{p['pair_id']}/notify"
    assert client.post(url, json={"title": "x"}, headers=auth(p["desktop_secret"])).status_code == 410
    status = client.get(f"/pairings/{p['pair_id']}", headers=auth(p["desktop_secret"])).json()
    assert status == {"paired": True, "phone_reachable": False}


def test_long_titles_and_bodies_are_truncated(env):
    client, sender, _ = env
    p, _ = paired(client)
    client.post(
        f"/pairings/{p['pair_id']}/notify",
        json={"title": "a" * 500, "body": "b" * 5000},
        headers=auth(p["desktop_secret"]),
    )
    assert len(sender.sent[0][1]) == 200
    assert len(sender.sent[0][2]) == 1000


def test_secrets_are_not_stored_in_plaintext(env, tmp_path):
    client, _, _ = env
    p, phone_secret = paired(client)
    raw = (tmp_path / "t.db").read_bytes()
    for secret in (p["desktop_secret"], phone_secret, p["pair_token"]):
        assert secret.encode() not in raw
