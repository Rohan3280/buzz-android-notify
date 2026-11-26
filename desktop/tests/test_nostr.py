import json

import pytest
from coincurve import PublicKeyXOnly

from aebuzz_desktop.nostr import (
    Keys,
    _padded_len,
    auth_event,
    bech32_decode,
    bech32_encode,
    conversation_key,
    event_id,
    nip44_decrypt,
)

# Vectors from Buzz's docs/nips/NIP-AE.md (sec1 = 0x01, sec2 = 0x02, as in NIP-44's own vectors).
SEC1 = bytes.fromhex("00" * 31 + "01")
PUBKEY_A = "79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
PUBKEY_O = "c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5"
K_C = "c41c775356fd92eadc63ff5a0dc1da211b268cbea22316767095b2871ea1412d"
D_EXAMPLE = "72d4f9629106451505d7d341ea85bb3ebad4f654fcfd2aad100d5a35f8a85cba"
EVENT1_CONTENT = (
    "AgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABedgcxyfmpph68LBjCWZsTI5lb0Cbg8dIPVYVe/WVj/l4Yd8HGgz"
    "C8awyBi9bn9ClRdtd2IPsmont0jN/cajVSQhahTOwuNNwoJtZIg35aSsUzeCq4tQfd8E+fLoKomdPxjs="
)


def test_pubkey_from_secret():
    assert Keys(SEC1).pubkey == PUBKEY_A


def test_nsec_round_trip():
    nsec = bech32_encode("nsec", SEC1)
    assert nsec.startswith("nsec1")
    assert bech32_decode(nsec) == ("nsec", SEC1)
    assert Keys.from_nsec(nsec).pubkey == PUBKEY_A


def test_bad_checksum_rejected():
    nsec = bech32_encode("nsec", SEC1)
    broken = nsec[:-1] + ("q" if nsec[-1] != "q" else "p")
    with pytest.raises(ValueError):
        bech32_decode(broken)


def test_npub_is_not_a_secret_key():
    with pytest.raises(ValueError):
        Keys.from_nsec(bech32_encode("npub", bytes.fromhex(PUBKEY_A)))


def test_repr_hides_secret():
    assert SEC1.hex() not in repr(Keys(SEC1))


def test_conversation_key_matches_nip44_vector():
    assert conversation_key(SEC1, PUBKEY_O).hex() == K_C


def test_decrypts_buzz_vector():
    assert json.loads(nip44_decrypt(EVENT1_CONTENT, bytes.fromhex(K_C))) == {
        "slug": "mem/example",
        "value": "hello, agent memory",
    }


def test_tampered_payload_rejected():
    tampered = EVENT1_CONTENT[:60] + ("A" if EVENT1_CONTENT[60] != "A" else "B") + EVENT1_CONTENT[61:]
    with pytest.raises(ValueError):
        nip44_decrypt(tampered, bytes.fromhex(K_C))


def test_event_id_matches_buzz_vector():
    tags = [["d", D_EXAMPLE], ["p", PUBKEY_O]]
    assert (
        event_id(PUBKEY_A, 1700000000, 30174, tags, EVENT1_CONTENT)
        == "f4a594177b7aeea4fe99a09efbf74ae85f0126244f322135682c405888a38689"
    )


def test_auth_event_is_validly_signed():
    ev = auth_event(Keys(SEC1), "wss://relay.example", "abc")
    assert ev["kind"] == 22242
    assert ev["tags"] == [["relay", "wss://relay.example"], ["challenge", "abc"]]
    assert ev["id"] == event_id(ev["pubkey"], ev["created_at"], 22242, ev["tags"], "")
    assert PublicKeyXOnly(bytes.fromhex(PUBKEY_A)).verify(
        bytes.fromhex(ev["sig"]), bytes.fromhex(ev["id"])
    )


@pytest.mark.parametrize(
    "n,expected", [(1, 32), (32, 32), (33, 64), (256, 256), (257, 320), (1000, 1024), (65535, 65536)]
)
def test_padding_lengths(n, expected):
    assert _padded_len(n) == expected
