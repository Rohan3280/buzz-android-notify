from aebuzz_desktop.config import Config, relay_url_from_storage

COMMUNITIES = (
    b'buzz-communities\x01[{"id":"https://chat.example.com","relayUrl":"wss://chat.example.com",'
    b'"name":"chat.example.com"}],"selected":"https://chat.example.com"'
)


def test_finds_relay_address_in_buzz_storage():
    assert relay_url_from_storage([COMMUNITIES]) == "wss://chat.example.com"


def test_ignores_addresses_with_a_path():
    assert relay_url_from_storage([b'"pairing":"wss://chat.example.com/pair"']) is None


def test_newest_blob_wins():
    older = b'"relayUrl":"wss://old.example.com"'
    newer = b'"relayUrl":"wss://new.example.com:8443"'
    assert relay_url_from_storage([newer, older]) == "wss://new.example.com:8443"


def test_nothing_found():
    assert relay_url_from_storage([b"", b"no address here"]) is None


def test_config_override_wins(monkeypatch):
    monkeypatch.setattr("aebuzz_desktop.config.detect_buzz_relay_url", lambda: "wss://detected.example")
    assert Config(buzz_relay_url="wss://override.example/").resolve_buzz_relay_url() == "wss://override.example"
    assert Config().resolve_buzz_relay_url() == "wss://detected.example"
