import pytest

from playlist_sync.providers import ProviderError, parse_url


@pytest.mark.parametrize("url, expected", [
    ("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc",
     ("spotify", "37i9dQZF1DXcBWIGoYBM5M")),
    ("https://open.spotify.com/intl-de/playlist/37i9dQZF1DXcBWIGoYBM5M",
     ("spotify", "37i9dQZF1DXcBWIGoYBM5M")),
    ("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M", ("spotify", "37i9dQZF1DXcBWIGoYBM5M")),
    ("https://music.youtube.com/playlist?list=PLabc-123_x", ("ytmusic", "PLabc-123_x")),
    ("https://www.youtube.com/watch?v=xyz&list=PLabc", ("ytmusic", "PLabc")),
    ("https://music.amazon.com/user-playlists/abc123", ("amazon", "abc123")),
])
def test_parse_url(url, expected):
    assert parse_url(url) == expected


def test_unknown_url():
    with pytest.raises(ProviderError):
        parse_url("https://example.com/playlist/1")


def test_playlist_url():
    from playlist_sync.providers import playlist_url

    assert playlist_url("spotify", "abc") == "https://open.spotify.com/playlist/abc"
    assert playlist_url("ytmusic", "PLx") == "https://music.youtube.com/playlist?list=PLx"
    assert playlist_url("csv", "x") is None
    assert playlist_url("spotify", None) is None
