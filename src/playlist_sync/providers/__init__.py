from __future__ import annotations

from .amazon import AmazonMusicProvider
from .base import Provider, ProviderError
from .csvfile import CsvFileProvider
from .spotify import SpotifyProvider
from .ytmusic import YTMusicProvider

PROVIDERS: dict[str, type[Provider]] = {
    p.name: p for p in (SpotifyProvider, YTMusicProvider, AmazonMusicProvider, CsvFileProvider)
}


def get_provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]()
    except KeyError:
        raise ProviderError(f"Unknown service {name!r}. Choose from: {', '.join(PROVIDERS)}") \
            from None


_PLAYLIST_URLS = {
    "spotify": "https://open.spotify.com/playlist/{id}",
    "ytmusic": "https://music.youtube.com/playlist?list={id}",
}


def playlist_url(service: str, playlist_id: str | None) -> str | None:
    """Web link to a playlist we created, for printing after copy/list."""
    template = _PLAYLIST_URLS.get(service)
    return template.format(id=playlist_id) if template and playlist_id else None


def parse_url(url: str) -> tuple[str, str]:
    """Return (service, playlist_id) for a playlist URL."""
    for name, cls in PROVIDERS.items():
        if playlist_id := cls.parse_playlist_id(url):
            return name, playlist_id
    raise ProviderError(f"Not a playlist URL I recognize: {url}")


__all__ = ["PROVIDERS", "Provider", "ProviderError", "get_provider", "parse_url", "playlist_url"]
