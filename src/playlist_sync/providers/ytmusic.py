"""YouTube Music.

Reading public playlists and searching use the unofficial `ytmusicapi` library and need
no login. Writing uses one of two logins:

- Google sign-in (default): the official YouTube Data API (see youtube_api.py).
- Browser headers (`auth ytmusic --browser`): ytmusicapi with your browser session.
  It has no daily quota, but the saved cookie grants full access to your account.
"""

from __future__ import annotations

import json
import re

from .. import credentials
from ..matching import interpretations, normalize_title
from ..models import Playlist, Track
from . import youtube_api
from .base import Provider, ProviderError, chunks

_URL = re.compile(r"(?:music\.)?youtube\.com/(?:playlist|watch)\?.*?list=([\w-]+)")


def has_browser_login() -> bool:
    return bool(credentials.get(credentials.YTMUSIC_BROWSER))


def browser_client():
    from ytmusicapi import YTMusic

    headers = credentials.get_json(credentials.YTMUSIC_BROWSER)
    if not headers:
        raise ProviderError("No YouTube Music browser login. Run: playlist-sync auth ytmusic "
                            "--browser")
    return YTMusic(auth=headers)


class YTMusicProvider(Provider):
    name = "ytmusic"

    def __init__(self):
        self._public = None
        self._writer = None

    @staticmethod
    def parse_playlist_id(url: str) -> str | None:
        m = _URL.search(url)
        return m.group(1) if m else None

    def _reader(self):
        from ytmusicapi import YTMusic

        if self._public is None:
            self._public = YTMusic()
        return self._public

    def _write_client(self):
        if self._writer is None:
            if youtube_api.is_logged_in():
                self._writer = youtube_api.YouTubeDataAPI()
            elif has_browser_login():
                self._writer = _BrowserWriter(browser_client())
            else:
                raise ProviderError("Not logged in to YouTube Music. Run: playlist-sync auth "
                                    "ytmusic")
        return self._writer

    def read_playlist(self, playlist_id: str) -> Playlist:
        try:
            data = self._reader().get_playlist(playlist_id, limit=None)
        except Exception as e:  # ytmusicapi raises bare exceptions for missing playlists.
            raise ProviderError(f"Couldn't read YouTube Music playlist {playlist_id}. "
                                f"Is it public? ({e})") from e
        tracks = [_track(t) for t in data.get("tracks", []) if t.get("videoId")]
        return Playlist(self.name, playlist_id, data.get("title", ""),
                        data.get("description") or "", tracks)

    def search_queries(self, track: Track) -> list[str]:
        return list(dict.fromkeys(
            f"{normalize_title(r.title)} {' '.join(r.artists[:2])}" for r in interpretations(track)
        ))

    def search(self, query: str) -> list[Track]:
        results = self._reader().search(query, filter="songs", limit=10)
        return [_track(r) for r in results if r.get("videoId")]

    def create_playlist(self, name: str, description: str, public: bool) -> str:
        return self._write_client().create_playlist(name, description, public)

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        self._write_client().add_tracks(playlist_id, track_ids)

    def remove_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        self._write_client().remove_tracks(playlist_id, track_ids)


class _BrowserWriter:
    def __init__(self, yt):
        self.yt = yt

    def create_playlist(self, name: str, description: str, public: bool) -> str:
        result = self.yt.create_playlist(
            name, description[:5000], privacy_status="PUBLIC" if public else "PRIVATE"
        )
        if not isinstance(result, str):
            raise ProviderError(f"YouTube Music refused to create the playlist: "
                                f"{json.dumps(result)[:200]}")
        return result

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        for batch in chunks(track_ids, 50):
            self.yt.add_playlist_items(playlist_id, batch, duplicates=False)

    def remove_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        wanted = set(track_ids)
        # Removal needs each entry's setVideoId, which only the playlist listing has.
        entries = self.yt.get_playlist(playlist_id, limit=None).get("tracks", [])
        to_remove = [e for e in entries if e.get("videoId") in wanted and e.get("setVideoId")]
        if to_remove:
            self.yt.remove_playlist_items(playlist_id, to_remove)


def _track(t: dict) -> Track:
    seconds = t.get("duration_seconds")
    return Track(
        title=t.get("title", ""),
        artists=tuple(a["name"] for a in t.get("artists") or [] if a.get("name")),
        album=(t.get("album") or {}).get("name"),
        duration_ms=seconds * 1000 if seconds else None,
        service_id=t["videoId"],
    )
