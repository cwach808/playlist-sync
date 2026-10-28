import json
import stat

import pytest

from playlist_sync import credentials


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYLIST_SYNC_HOME", str(tmp_path))
    monkeypatch.setattr(credentials, "_keyring", lambda: None)  # Never touch the real keychain.
    monkeypatch.setattr(credentials, "_memory", {})
    credentials.set_session_only(False)
    yield tmp_path
    credentials.set_session_only(False)


def test_file_fallback_is_private(isolated, capsys):
    credentials.put("spotify-token", "abc")
    path = isolated / "credentials.json"
    assert json.loads(path.read_text()) == {"spotify-token": "abc"}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert credentials.get("spotify-token") == "abc"
    assert "no OS keychain" in capsys.readouterr().err


def test_env_var_wins_and_is_never_written(isolated, monkeypatch):
    monkeypatch.setenv("PLAYLIST_SYNC_SPOTIFY_TOKEN", "from-env")
    assert credentials.get("spotify-token") == "from-env"
    credentials.put("spotify-token", "refreshed")  # e.g. a token refresh in CI
    assert not (isolated / "credentials.json").exists()


def test_session_only_keeps_nothing_on_disk(isolated):
    credentials.set_session_only(True)
    credentials.put("google-token", "t")
    assert credentials.get("google-token") == "t"
    assert not (isolated / "credentials.json").exists()


def test_delete(isolated):
    credentials.put_json("google-token", {"a": 1})
    assert credentials.get_json("google-token") == {"a": 1}
    credentials.delete("google-token")
    assert credentials.get("google-token") is None


def test_youtube_api_errors_are_explained():
    from playlist_sync.providers.youtube_api import _ApiError

    assert "isn't enabled" in _ApiError(403, "accessNotConfigured", "").user_message()
    assert "no YouTube channel" in _ApiError(403, "youtubeSignupRequired", "").user_message()
    assert "quota" in _ApiError(403, "quotaExceeded", "").user_message()
