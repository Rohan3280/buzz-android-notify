from aebuzz_desktop.config import Config
from aebuzz_desktop.local_server import LocalServer


def test_does_nothing_when_laptop_does_not_host_the_server():
    server = LocalServer(Config())
    assert not server.enabled
    assert server.ensure_running() is None
    server.stop()  # no-op, must not raise


def test_reports_missing_server_install(tmp_path):
    cfg = Config(server_url="http://127.0.0.1:9", local_server_dir=str(tmp_path))
    assert "not found" in LocalServer(cfg).ensure_running()


def test_new_config_fields_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    Config(local_server_dir="C:/srv", firebase_key_path="C:/key.json").save(path)
    loaded = Config.load(path)
    assert loaded.local_server_dir == "C:/srv" and loaded.firebase_key_path == "C:/key.json"
