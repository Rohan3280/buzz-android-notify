"""Reads the Buzz sign-in key that the Buzz desktop app saved in Windows Credential Manager.

The key stays on this laptop: it is only used to sign in to the Buzz server and
to decrypt the user's own mute list. It is never logged or sent anywhere else.
"""
from __future__ import annotations

import ctypes
import json
from ctypes import wintypes

from .nostr import Keys

# Buzz desktop keeps a JSON map under "secrets.buzz-desktop" (the human key is
# its "identity" entry); Buzz Foundation also saves the key on its own.
_BLOB_TARGET = "secrets.buzz-desktop"
_IDENTITY_TARGETS = ("human.xyz.block.buzz.desktop.identity",)
_CRED_TYPE_GENERIC = 1


class BuzzKeyMissing(Exception):
    pass


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _read_credential(target: str) -> str | None:
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_Credential)),
    ]
    advapi.CredFree.argtypes = [ctypes.c_void_p]
    cred = ctypes.POINTER(_Credential)()
    if not advapi.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(cred)):
        return None
    try:
        blob = ctypes.string_at(cred.contents.CredentialBlob, cred.contents.CredentialBlobSize)
    finally:
        advapi.CredFree(cred)
    # The keyring library Buzz uses stores text as UTF-16LE.
    return blob.decode("utf-16-le").strip()


def _candidates():
    blob = _read_credential(_BLOB_TARGET)
    if blob:
        try:
            identity = json.loads(blob).get("identity")
        except ValueError:
            identity = None
        if isinstance(identity, str):
            yield identity
    for target in _IDENTITY_TARGETS:
        value = _read_credential(target)
        if value:
            yield value


def load_buzz_keys() -> Keys:
    for candidate in _candidates():
        try:
            return Keys.from_nsec(candidate)
        except ValueError:
            continue
    raise BuzzKeyMissing(
        "Couldn't find your Buzz key on this laptop. Sign in to the Buzz desktop app, "
        "then restart AE Buzz."
    )
