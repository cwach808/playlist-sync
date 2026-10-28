"""Where logins live.

Lookup order for each credential:
  1. Environment variable PLAYLIST_SYNC_<NAME> (for CI, where there's no keychain).
  2. The OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service).
  3. If no keychain is available: a file in the state dir readable only by you.

With --no-save, everything stays in memory for the current run only.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import sys
from pathlib import Path

SERVICE = "playlist-sync"

# Known credential names, for `doctor` and `auth logout`. These are the labels the
# values are filed under in the keychain, not the secrets themselves, so the bandit
# "hardcoded password" warnings (B105) on them are false positives.
SPOTIFY_CLIENT_ID = "spotify-client-id"
SPOTIFY_TOKEN = "spotify-token"  # nosec B105
GOOGLE_CLIENT = "google-client"
GOOGLE_TOKEN = "google-token"  # nosec B105
YTMUSIC_BROWSER = "ytmusic-browser"
ALL = (SPOTIFY_CLIENT_ID, SPOTIFY_TOKEN, GOOGLE_CLIENT, GOOGLE_TOKEN, YTMUSIC_BROWSER)

_memory: dict[str, str] = {}
_session_only = False
_warned_fallback = False


def set_session_only(enabled: bool) -> None:
    global _session_only
    _session_only = enabled


def env_var(name: str) -> str:
    return "PLAYLIST_SYNC_" + name.upper().replace("-", "_")


def _fallback_file() -> Path:
    from .store import home_dir

    return home_dir() / "credentials.json"


def _read_fallback() -> dict[str, str]:
    path = _fallback_file()
    return json.loads(path.read_text()) if path.exists() else {}


def _write_fallback(data: dict[str, str]) -> None:
    global _warned_fallback
    path = _fallback_file()
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    path.write_text(json.dumps(data, indent=2))
    if not _warned_fallback:
        _warned_fallback = True
        print(f"warning: no OS keychain available; saved credentials to {path} "
              "(readable only by you).", file=sys.stderr)


def _keyring():
    """Return the keyring module if a real backend is available, else None."""
    try:
        import keyring
        from keyring.backends import fail

        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring
    except Exception:
        return None


def backend_name() -> str:
    if _session_only:
        return "memory (--no-save)"
    kr = _keyring()
    if kr:
        return f"OS keychain ({type(kr.get_keyring()).__module__.rsplit('.', 1)[-1]})"
    return f"file ({_fallback_file()})"


def get(name: str) -> str | None:
    if value := os.environ.get(env_var(name)):
        return value
    if name in _memory:
        return _memory[name]
    if _session_only:
        return None
    if kr := _keyring():
        from keyring.errors import KeyringError

        try:
            if (value := kr.get_password(SERVICE, name)) is not None:
                return value
        except KeyringError:
            pass  # Keychain locked or unavailable: fall through to the private file.
    return _read_fallback().get(name)


def put(name: str, value: str) -> None:
    if os.environ.get(env_var(name)) or _session_only:
        # Env-provided creds (CI) can't be written back; keep refreshed values for this run.
        _memory[name] = value
        return
    if kr := _keyring():
        from keyring.errors import KeyringError

        try:
            kr.set_password(SERVICE, name, value)
            return
        except KeyringError:
            pass  # e.g. Windows' ~2.5 KB limit on browser-header blobs; use the file.
    data = _read_fallback()
    data[name] = value
    _write_fallback(data)


def delete(name: str) -> None:
    _memory.pop(name, None)
    if kr := _keyring():
        from keyring.errors import KeyringError

        with contextlib.suppress(KeyringError):  # Includes "nothing saved under that name".
            kr.delete_password(SERVICE, name)
    data = _read_fallback()
    if data.pop(name, None) is not None:
        _write_fallback(data)


def get_json(name: str) -> dict | None:
    value = get(name)
    return json.loads(value) if value else None


def put_json(name: str, value: dict) -> None:
    put(name, json.dumps(value))


def can_prompt() -> bool:
    return sys.stdin.isatty()
