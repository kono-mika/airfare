"""API keys at rest, kept out of config.json in plain text where the system allows it.

Windows: encrypted with DPAPI, so only this Windows account on this PC can read them. config.json stores each
key as "dpapi:" and the encrypted bytes in base64. Windows ties the encryption to the signed-in account (its
login password protects the master key); copied to another PC or user, the value can't be decrypted and the
key has to be entered again.

macOS and Linux: the key goes to the user's keychain (the login Keychain through `security` on macOS; the
Secret Service, such as GNOME Keyring or KWallet, through `secret-tool` on Linux), as the password of the
entry service "AirFare", account <the key's name>. config.json stores only "keychain:<name>:<tag>", where the
tag changes with every new key so that other AirFare processes notice the change. Copied to another computer
or user, the entry isn't there and the key has to be entered again, as on Windows. Where there's no keychain
to use (a Linux without secret-tool or a keyring, a locked Keychain over SSH) the key stays in config.json as
plain text, which config.save_config makes readable by this user only.
"""
from __future__ import annotations

import base64
import binascii
import ctypes
import logging
import os
import subprocess

from . import platform

if platform.WINDOWS:
    from ctypes import wintypes

log = logging.getLogger(__name__)

PREFIX = "dpapi:"
KEYCHAIN = "keychain:"
ENTROPY = b"AirFare API keys"        # an extra secret mixed in, so other programs' DPAPI calls don't fit
UI_FORBIDDEN = 0x1                   # CRYPTPROTECT_UI_FORBIDDEN: never show a prompt (the service has no window)
SERVICE = "AirFare"                  # the keychain entries' service name
# Who can read the keys, as messages name it.
ACCOUNT = "this Windows account" if platform.WINDOWS else "this account"


class SecretError(Exception):
    """A stored key that can't be decrypted here: damaged, or encrypted by another Windows account or PC (or,
    on macOS and Linux, not in this account's keychain)."""


if platform.WINDOWS:
    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_Blob, ctypes.Array]:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _crypt(name: str, data: bytes) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = getattr(crypt32, name)
    fn.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    fn.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    (src, src_buf), (extra, extra_buf), out = _blob(data), _blob(ENTROPY), _Blob()
    if not fn(ctypes.byref(src), None, ctypes.byref(extra), None, None, UI_FORBIDDEN, ctypes.byref(out)):
        raise SecretError(f"{name} failed: {ctypes.FormatError(ctypes.get_last_error()).strip()}")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def protected(text) -> bool:
    return isinstance(text, str) and text.startswith((PREFIX, KEYCHAIN))


def protect(text: str, name: str = "") -> str:
    """The key as stored in config.json: encrypted for this Windows account, or a reference to the keychain
    entry `name` (macOS, Linux; plain text when there's no keychain). Empty stays empty, and a value that is
    already protected is returned as it is."""
    if not text or protected(text):
        return text or ""
    if not platform.WINDOWS:
        return _to_keychain(name or "api_key", text)
    return PREFIX + base64.b64encode(_crypt("CryptProtectData", text.encode("utf-8"))).decode("ascii")


def unprotect(text: str) -> str:
    """The key itself. A plain value (config.json from before keys were encrypted) is returned unchanged;
    one that can't be decrypted here raises SecretError."""
    if not protected(text):
        return text or ""
    if text.startswith(KEYCHAIN):
        if platform.WINDOWS:
            raise SecretError("kept in the keychain of a Mac or Linux computer")
        return _from_keychain(text)
    if not platform.WINDOWS:
        raise SecretError("encrypted by Windows on another computer")
    try:
        data = base64.b64decode(text[len(PREFIX):], validate=True)
    except (binascii.Error, ValueError):
        raise SecretError("not valid base64") from None
    if not data:
        raise SecretError("empty value")
    try:
        return _crypt("CryptUnprotectData", data).decode("utf-8")
    except UnicodeDecodeError:
        raise SecretError("not a key") from None


# ----- the keychain (macOS, Linux) -------------------------------------------------------------------------

# Settings load on every page request, so each process asks the keychain once per stored value: the key for
# each "keychain:" value read or written, and the last key each name was saved or read with.
_cache: dict[str, str] = {}
_last: dict[str, tuple[str, str]] = {}
_warned_plain = False


def _keychain_get(name: str) -> str | None:
    """The key saved under `name`, or None when there is none (or no keychain to ask)."""
    cmd = (["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"] if platform.MACOS else
           ["secret-tool", "lookup", "service", SERVICE, "key", name])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = r.stdout.rstrip("\n")
    return value if r.returncode == 0 and value else None


def _keychain_set(name: str, value: str) -> bool:
    """Save the key under `name`, replacing an earlier one. False when there's no keychain to use."""
    if platform.MACOS:
        # security takes the password as an argument: only this user's own processes can see those on macOS.
        cmd, data = ["security", "add-generic-password", "-U", "-s", SERVICE, "-a", name, "-l", f"{SERVICE} {name}",
                     "-w", value], None
    else:
        cmd, data = ["secret-tool", "store", f"--label={SERVICE} {name}", "service", SERVICE, "key", name], value
    try:
        r = subprocess.run(cmd, input=data, capture_output=True, text=True, encoding="utf-8", timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.debug("keychain: %s", e)
        return False
    if r.returncode != 0:
        log.debug("keychain: %s", (r.stderr or r.stdout).strip()[:200])
    return r.returncode == 0


def _to_keychain(name: str, text: str) -> str:
    global _warned_plain
    last = _last.get(name)
    if last and last[0] == text:
        return last[1]
    if not _keychain_set(name, text):
        if not _warned_plain:
            _warned_plain = True
            log.warning("no keychain to keep the API keys in (%s); they stay in config.json, readable by this "
                        "user only", "Keychain locked?" if platform.MACOS else "is secret-tool installed?")
        return text
    stored = f"{KEYCHAIN}{name}:{os.urandom(4).hex()}"
    _cache[stored] = text
    _last[name] = (text, stored)
    return stored


def _from_keychain(stored: str) -> str:
    if stored in _cache:
        return _cache[stored]
    name = stored[len(KEYCHAIN):].rsplit(":", 1)[0]
    value = _keychain_get(name) if name else None
    if value is None:
        raise SecretError("not in this account's keychain")
    _cache[stored] = value
    _last[name] = (value, stored)
    return value
