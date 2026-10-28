import json
import threading

import httpx

from aebuzz_desktop.config import Config
from aebuzz_desktop.relay import Forwarder, RelayClient
from aebuzz_desktop.toasts import Toast


def client_with(handler, base="http://127.0.0.1:8000"):
    c = RelayClient(base)
    c._http = httpx.Client(base_url=base, transport=httpx.MockTransport(handler))
    return c


def test_qr_payload_uses_public_url_when_server_has_one():
    def handler(req):
        return httpx.Response(200, json={"pair_id": "p1", "desktop_secret": "d", "pair_token": "t",
                                         "expires_at": 0, "public_url": "https://abc.trycloudflare.com"})
    p = client_with(handler).create_pairing()
    assert json.loads(p.qr_payload) == {"v": 1, "server": "https://abc.trycloudflare.com", "pair": "p1", "token": "t"}


def test_qr_payload_carries_firebase_options():
    fb = {"api_key": "k", "app_id": "a", "project_id": "p", "sender_id": "s"}

    def handler(req):
        return httpx.Response(200, json={"pair_id": "p1", "desktop_secret": "d", "pair_token": "t",
                                         "expires_at": 0, "public_url": "https://x.test", "firebase": fb})
    assert json.loads(client_with(handler).create_pairing().qr_payload)["fb"] == fb


def test_qr_payload_falls_back_to_server_url():
    def handler(req):
        return httpx.Response(200, json={"pair_id": "p1", "desktop_secret": "d", "pair_token": "t",
                                         "expires_at": 0, "public_url": None})
    assert client_with(handler).create_pairing().phone_url == "http://127.0.0.1:8000"


def test_config_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    Config(pair_id="p", desktop_secret="s", paused=True).save(path)
    loaded = Config.load(path)
    assert loaded.paired and loaded.paused


def test_forwarder_skips_when_paused_or_unpaired():
    cfg = Config()
    f = Forwarder(cfg, lambda url: None, lambda s: None, lambda: None)
    f.submit(Toast("x", None))
    assert f._queue.empty()
    cfg.pair_id, cfg.desktop_secret, cfg.paused = "p", "s", True
    f.submit(Toast("x", None))
    assert f._queue.empty()


def test_forwarder_reports_unpaired_on_410():
    cfg = Config(pair_id="p", desktop_secret="s")
    done = threading.Event()
    seen = []

    def handler(req):
        body = json.loads(req.content)
        seen.append((body["title"], body["body"]))
        return httpx.Response(410)

    f = Forwarder(cfg, lambda url: client_with(handler), lambda s: None, done.set)
    f.start()
    f.submit(Toast("Sooraj in #backend", "deploy failed"))
    assert done.wait(5)
    assert seen == [("Sooraj in #backend", "deploy failed")]


def test_config_with_bom_from_powershell(tmp_path):
    path = tmp_path / "config.json"
    path.write_bytes(b'\xef\xbb\xbf{"local_server_dir": "C:/srv"}')
    assert Config.load(path).local_server_dir == "C:/srv"
