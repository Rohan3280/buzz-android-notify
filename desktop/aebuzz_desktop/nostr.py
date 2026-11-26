"""Just enough Nostr for AE Buzz: key decoding, event signing and NIP-44 decryption.

Buzz is built on Nostr. AE Buzz signs in to the Buzz server as the user (NIP-42),
and decrypts the user's mute list, which Buzz stores NIP-44-encrypted to the
user's own key.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
from dataclasses import dataclass

from coincurve import PrivateKey, PublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms

# ── bech32 (BIP-173), for nsec / npub strings ──────────────────────────────────

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _polymod(values: list[int]) -> int:
    gen = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if (top >> i) & 1 else 0
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _convert_bits(data, from_bits: int, to_bits: int, pad: bool) -> list[int]:
    acc = bits = 0
    out = []
    maxv = (1 << to_bits) - 1
    for value in data:
        acc = (acc << from_bits) | value
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            out.append((acc >> bits) & maxv)
    if pad and bits:
        out.append((acc << (to_bits - bits)) & maxv)
    elif not pad and (bits >= from_bits or (acc << (to_bits - bits)) & maxv):
        raise ValueError("invalid bech32 padding")
    return out


def bech32_decode(text: str) -> tuple[str, bytes]:
    """Returns (prefix, 32-byte payload) for nsec/npub strings."""
    text = text.strip().lower()
    hrp, sep, data = text.rpartition("1")
    if not sep or not hrp or len(data) < 6 or any(c not in _CHARSET for c in data):
        raise ValueError("not a bech32 string")
    values = [_CHARSET.index(c) for c in data]
    if _polymod(_hrp_expand(hrp) + values) != 1:
        raise ValueError("bad bech32 checksum")
    return hrp, bytes(_convert_bits(values[:-6], 5, 8, False))


def bech32_encode(hrp: str, payload: bytes) -> str:
    values = _convert_bits(payload, 8, 5, True)
    poly = _polymod(_hrp_expand(hrp) + values + [0] * 6) ^ 1
    checksum = [(poly >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_CHARSET[v] for v in values + checksum)


# ── keys and events ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Keys:
    secret: bytes  # 32 bytes

    @classmethod
    def from_nsec(cls, nsec: str) -> "Keys":
        hrp, payload = bech32_decode(nsec)
        if hrp != "nsec" or len(payload) != 32:
            raise ValueError("not an nsec key")
        return cls(payload)

    @property
    def pubkey(self) -> str:
        """x-only public key, lowercase hex (Nostr's form)."""
        return PrivateKey(self.secret).public_key_xonly.format().hex()

    def __repr__(self) -> str:  # never print the secret
        return f"Keys(pubkey={self.pubkey})"


def event_id(pubkey: str, created_at: int, kind: int, tags: list, content: str) -> str:
    serial = json.dumps(
        [0, pubkey, created_at, kind, tags, content], separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(serial.encode("utf-8")).hexdigest()


def sign_event(
    keys: Keys, kind: int, tags: list, content: str = "", created_at: int | None = None
) -> dict:
    created_at = int(time.time()) if created_at is None else created_at
    pubkey = keys.pubkey
    eid = event_id(pubkey, created_at, kind, tags, content)
    sig = PrivateKey(keys.secret).sign_schnorr(bytes.fromhex(eid), os.urandom(32))
    return {
        "id": eid,
        "pubkey": pubkey,
        "created_at": created_at,
        "kind": kind,
        "tags": tags,
        "content": content,
        "sig": sig.hex(),
    }


def auth_event(keys: Keys, relay_url: str, challenge: str) -> dict:
    """NIP-42 sign-in event."""
    return sign_event(keys, 22242, [["relay", relay_url], ["challenge", challenge]])


# ── NIP-44 v2 decryption ───────────────────────────────────────────────────────


def conversation_key(secret: bytes, pubkey_hex: str) -> bytes:
    shared = PublicKey(b"\x02" + bytes.fromhex(pubkey_hex)).multiply(secret)
    shared_x = shared.format(compressed=True)[1:]
    return hmac.new(b"nip44-v2", shared_x, hashlib.sha256).digest()  # HKDF-extract


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    out, block, counter = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def _padded_len(n: int) -> int:
    if n <= 32:
        return 32
    next_power = 1 << (n - 1).bit_length()
    chunk = 32 if next_power <= 256 else next_power // 8
    return chunk * ((n - 1) // chunk + 1)


def nip44_decrypt(payload: str, conv_key: bytes) -> str:
    raw = base64.b64decode(payload)
    if len(raw) < 99 or raw[0] != 2:
        raise ValueError("unsupported NIP-44 payload")
    nonce, ciphertext, mac = raw[1:33], raw[33:-32], raw[-32:]
    keys = _hkdf_expand(conv_key, nonce, 76)
    chacha_key, chacha_nonce, hmac_key = keys[:32], keys[32:44], keys[44:]
    expected = hmac.new(hmac_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, mac):
        raise ValueError("NIP-44 MAC mismatch")
    cipher = Cipher(algorithms.ChaCha20(chacha_key, b"\x00\x00\x00\x00" + chacha_nonce), mode=None)
    padded = cipher.decryptor().update(ciphertext)
    (length,) = struct.unpack(">H", padded[:2])
    if length == 0 or len(padded) != 2 + _padded_len(length):
        raise ValueError("bad NIP-44 padding")
    return padded[2 : 2 + length].decode("utf-8")


def nip44_decrypt_from_self(keys: Keys, payload: str) -> str:
    return nip44_decrypt(payload, conversation_key(keys.secret, keys.pubkey))
