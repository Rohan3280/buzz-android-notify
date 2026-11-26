import sys

import pytest

from aebuzz_desktop.tunnel import QuickTunnel, TunnelError, TUNNEL_URL_RE, is_local_url


def test_local_urls():
    assert is_local_url("http://127.0.0.1:8000")
    assert is_local_url("http://localhost:8000")
    assert not is_local_url("https://relay.example.com")


def test_finds_quick_tunnel_address_in_cloudflared_log():
    line = "2026-11-26T10:00:00Z INF |  https://able-baker-charlie.trycloudflare.com                    |"
    assert TUNNEL_URL_RE.search(line).group(0) == "https://able-baker-charlie.trycloudflare.com"


def test_missing_cloudflared(monkeypatch):
    monkeypatch.setattr("aebuzz_desktop.tunnel.find_cloudflared", lambda: None)
    with pytest.raises(TunnelError, match="isn't installed"):
        QuickTunnel("http://127.0.0.1:8000").start()


def test_cloudflared_that_never_prints_an_address(monkeypatch, tmp_path):
    # A stand-in "cloudflared" that exits without printing a tunnel address.
    monkeypatch.setattr("aebuzz_desktop.tunnel.START_TIMEOUT_SECONDS", 5)
    fake = tmp_path / "fake_cloudflared.py"
    fake.write_text("import sys; print('starting', file=sys.stderr)")
    tunnel = QuickTunnel("http://127.0.0.1:8000", executable=sys.executable)
    monkeypatch.setattr(
        "aebuzz_desktop.tunnel.subprocess.Popen",
        _popen_running(str(fake)),
    )
    with pytest.raises(TunnelError, match="didn't start"):
        tunnel.start()


def _popen_running(script):
    import subprocess

    real = subprocess.Popen

    def popen(args, **kwargs):
        return real([sys.executable, script], **kwargs)

    return popen
