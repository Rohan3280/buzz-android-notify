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


def test_bundled_exe_runs_its_own_server(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:/Apps/AE Buzz.exe")
    monkeypatch.setattr("aebuzz_desktop.local_server.config_path", lambda: tmp_path / "config.json")
    server = LocalServer(Config(firebase_key_path="C:/key.json"))
    assert server.enabled
    assert server.command() == (["C:/Apps/AE Buzz.exe", "--relay-server"], tmp_path)


def test_bundled_exe_without_firebase_key_hosts_nothing(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert not LocalServer(Config()).enabled


def test_source_install_wins_when_configured(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    cfg = Config(local_server_dir=str(tmp_path), firebase_key_path="C:/key.json")
    assert "not found" in LocalServer(cfg).command()
