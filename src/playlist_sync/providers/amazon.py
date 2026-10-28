"""Amazon Music placeholder.

Amazon's Web API is invite-only, so there's no supported way to read or write playlists
directly. We recognize the URLs so users are pointed to the CSV exporter (see
playlist_sync/amazon/) instead of getting "unknown service".
"""

from __future__ import annotations

import re

from ..models import Playlist, Track
from .base import Provider, ProviderError

_URL = re.compile(r"music\.amazon\.[a-z.]+/(?:user-)?playlists/(\w+)")

_MSG = (
    "Amazon Music has no public API, so playlist-sync can't read Amazon links directly. "
    "Export the playlist to CSV instead: run `playlist-sync amazon-export` for the "
    "one-click exporter, then `playlist-sync copy FILE.csv --to spotify`."
)


class AmazonMusicProvider(Provider):
    name = "amazon"

    @staticmethod
    def parse_playlist_id(url: str) -> str | None:
        m = _URL.search(url)
        return m.group(1) if m else None

    def read_playlist(self, playlist_id: str) -> Playlist:
        raise ProviderError(_MSG)

    def search_queries(self, track: Track) -> list[str]:
        raise ProviderError(_MSG)

    def search(self, query: str) -> list[Track]:
        raise ProviderError(_MSG)

    def create_playlist(self, name: str, description: str, public: bool) -> str:
        raise ProviderError(_MSG)

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        raise ProviderError(_MSG)

    def remove_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        raise ProviderError(_MSG)
