"""Spotify via the Web API (Feb 2026 rules), plus the public embed page for reading.

Login uses PKCE, so users only need their app's Client ID (no secret), and tokens are
kept in the OS keychain (see credentials.py).

Since Feb 2026, Development Mode apps only get the *contents* of playlists the user owns
or collaborates on. To read anyone else's public playlist we fall back to the public
embed page, which needs no credentials but may not include every track of very long
playlists.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

import httpx
from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyOAuth, SpotifyPKCE

from .. import credentials
from ..matching import interpretations, normalize_title
from ..models import Playlist, Track
from .base import PartialWriteError, Provider, ProviderError, chunks

API = "https://api.spotify.com/v1"
SCOPES = "playlist-read-private playlist-modify-private playlist-modify-public"
DEFAULT_REDIRECT = "http://127.0.0.1:8888/callback"
MAX_RATE_LIMIT_WAIT = 120  # seconds; longer waits stop the run instead of looking frozen

_URL = re.compile(r"(?:open\.spotify\.com/(?:intl-[a-z]+/)?playlist/|spotify:playlist:)(\w+)")
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class _KeychainCache(CacheHandler):
    def get_cached_token(self):
        return credentials.get_json(credentials.SPOTIFY_TOKEN)

    def save_token_to_cache(self, token_info):
        credentials.put_json(credentials.SPOTIFY_TOKEN, token_info)


def client_id() -> str | None:
    return os.environ.get("SPOTIFY_CLIENT_ID") or credentials.get(credentials.SPOTIFY_CLIENT_ID)


def auth_manager(open_browser: bool = True):
    """PKCE login (Client ID only) by default.

    If SPOTIFY_CLIENT_SECRET is set we use the classic flow instead. Its refresh token
    doesn't rotate, which suits CI runners that can't save a new token back.
    """
    cid = client_id()
    if not cid:
        raise ProviderError("Spotify isn't set up. Run: playlist-sync auth spotify")
    common = dict(
        client_id=cid,
        redirect_uri=os.environ.get("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT),
        scope=SCOPES,
        cache_handler=_KeychainCache(),
        open_browser=open_browser,
    )
    if secret := os.environ.get("SPOTIFY_CLIENT_SECRET"):
        return SpotifyOAuth(client_secret=secret, **common)
    return SpotifyPKCE(**common)


def access_token(manager, check_cache: bool = True) -> str:
    # SpotifyOAuth defaults to returning a dict; SpotifyPKCE has no as_dict parameter.
    if isinstance(manager, SpotifyOAuth):
        return manager.get_access_token(as_dict=False, check_cache=check_cache)
    return manager.get_access_token(check_cache=check_cache)


def is_logged_in() -> bool:
    return bool(client_id() and credentials.get(credentials.SPOTIFY_TOKEN))


def login(new_client_id: str | None = None) -> None:
    """Interactive browser login; stores the token in the keychain."""
    if new_client_id:
        credentials.put(credentials.SPOTIFY_CLIENT_ID, new_client_id.strip())
    access_token(auth_manager(), check_cache=False)


class SpotifyProvider(Provider):
    name = "spotify"

    def __init__(self):
        self._auth = None
        self._http = httpx.Client(timeout=30)

    @staticmethod
    def parse_playlist_id(url: str) -> str | None:
        m = _URL.search(url)
        return m.group(1) if m else None

    # HTTP

    def _request(self, method: str, path: str, **kwargs) -> dict:
        if self._auth is None:
            if not is_logged_in():
                if not credentials.can_prompt():
                    raise ProviderError("Not logged in to Spotify. Run: playlist-sync auth spotify")
                login()
            self._auth = auth_manager()
        for _ in range(5):
            token = access_token(self._auth)
            resp = self._http.request(
                method, f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", "2")) + 1
                if wait > MAX_RATE_LIMIT_WAIT:
                    raise ProviderError(
                        f"Spotify asked us to pause for {wait // 60} minutes (rate limit). "
                        "Progress is saved; run the same command again later."
                    )
                print(f"  Spotify asked us to slow down; waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                raise ProviderError(f"Spotify {method} {path} failed ({resp.status_code}): "
                                    f"{resp.text[:200]}")
            return resp.json() if resp.content else {}
        raise ProviderError("Spotify kept rate-limiting us; try again later.")

    # reading

    def read_playlist(self, playlist_id: str) -> Playlist:
        if is_logged_in():
            try:
                return self._read_via_api(playlist_id)
            except ProviderError:
                pass  # Not ours (403) or other API refusal; the embed may still work.
        return self._read_via_embed(playlist_id)

    def _read_via_api(self, playlist_id: str) -> Playlist:
        meta = self._request("GET", f"/playlists/{playlist_id}", params={
            "fields": "name,description",
        })
        tracks: list[Track] = []
        offset = 0
        while True:
            page = self._request("GET", f"/playlists/{playlist_id}/items",
                                 params={"limit": 50, "offset": offset})
            for entry in page.get("items", []):
                # Feb 2026 renamed `track` to `item`; accept either.
                t = entry.get("item") or entry.get("track")
                if t and t.get("type", "track") == "track" and t.get("uri"):
                    tracks.append(_track_from_api(t))
            if not page.get("next"):
                break
            offset += 50
        return Playlist(self.name, playlist_id, meta.get("name", ""),
                        meta.get("description") or "", tracks)

    def _read_via_embed(self, playlist_id: str) -> Playlist:
        resp = self._http.get(
            f"https://open.spotify.com/embed/playlist/{playlist_id}",
            headers={"User-Agent": "Mozilla/5.0 (playlist-sync)"},
        )
        m = _NEXT_DATA.search(resp.text)
        if resp.status_code != 200 or not m:
            raise ProviderError(
                f"Couldn't read Spotify playlist {playlist_id}. Is it public?"
            )
        try:
            entity = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
        except (KeyError, json.JSONDecodeError) as e:
            raise ProviderError("Spotify's embed page format changed; please file an issue.") \
                from e
        tracks = [
            Track(
                title=t["title"],
                artists=tuple(a.strip() for a in t.get("subtitle", "").split(",") if a.strip()),
                duration_ms=t.get("duration"),
                service_id=t["uri"],
            )
            for t in entity.get("trackList", [])
            if t.get("uri", "").startswith("spotify:track:")
        ]
        # The embed doesn't report the full count, so we can't tell for sure if it's cut off.
        return Playlist(self.name, playlist_id, entity.get("name", ""), "", tracks,
                        truncated=len(tracks) >= 100)

    # searching

    def search_queries(self, track: Track) -> list[str]:
        readings = [(normalize_title(r.title), r.artists[0] if r.artists else "")
                    for r in interpretations(track)]
        queries = [f"isrc:{track.isrc}"] if track.isrc else []
        # Field-targeted searches first (precise), then plain ones (forgiving).
        queries += [f'track:"{title}" artist:"{artist}"' for title, artist in readings]
        queries += [f"{title} {artist}" for title, artist in readings]
        return list(dict.fromkeys(queries))

    def search(self, query: str) -> list[Track]:
        data = self._request("GET", "/search", params={"q": query, "type": "track", "limit": 10})
        return [_track_from_api(t) for t in data.get("tracks", {}).get("items", []) if t]

    # writing

    def create_playlist(self, name: str, description: str, public: bool) -> str:
        data = self._request("POST", "/me/playlists", json={
            "name": name, "description": description[:300], "public": public,
        })
        if not public and data.get("public"):
            # Spotify sometimes ignores `public` on create; set it again explicitly.
            self._request("PUT", f"/playlists/{data['id']}", json={"public": False})
        return data["id"]

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        done: list[str] = []
        for batch in chunks(track_ids, 100):
            try:
                self._request("POST", f"/playlists/{playlist_id}/items", json={"uris": batch})
            except ProviderError as e:
                raise PartialWriteError(str(e), done) from e
            done.extend(batch)

    def remove_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        for batch in chunks(track_ids, 100):
            self._request("DELETE", f"/playlists/{playlist_id}/items",
                          json={"items": [{"uri": u} for u in batch]})


def _track_from_api(t: dict) -> Track:
    return Track(
        title=t.get("name", ""),
        artists=tuple(a["name"] for a in t.get("artists", [])),
        album=(t.get("album") or {}).get("name"),
        duration_ms=t.get("duration_ms"),
        isrc=(t.get("external_ids") or {}).get("isrc"),  # Only for Extended Quota apps now.
        service_id=t.get("uri"),
    )
