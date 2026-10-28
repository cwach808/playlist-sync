"""Official YouTube Data API v3, used to write to the user's YouTube Music library.

Google sign-in happens in the browser, and the token is stored via credentials.py.
Quota: projects get 10,000 units/day by default. Creating a playlist or adding or
removing one item costs 50 units, so roughly 200 track adds per day. Searching goes
through ytmusicapi instead and costs no quota.
"""

from __future__ import annotations

import contextlib
import json
import sys

import httpx

from .. import credentials
from .base import PartialWriteError, ProviderError

API = "https://www.googleapis.com/youtube/v3"
SCOPES = ["https://www.googleapis.com/auth/youtube"]


def load_client_file(path: str) -> dict:
    """Read the OAuth client JSON downloaded from Google Cloud Console."""
    with open(path) as f:
        config = json.load(f)
    if "installed" not in config:
        raise ProviderError(
            "That file isn't a Desktop app OAuth client. In Google Cloud Console create "
            "credentials of type 'OAuth client ID' > 'Desktop app'."
        )
    return config


def is_logged_in() -> bool:
    return bool(credentials.get(credentials.GOOGLE_TOKEN))


def login(client_config: dict | None = None) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow, WSGITimeoutError

    if client_config:
        credentials.put_json(credentials.GOOGLE_CLIENT, client_config)
    config = credentials.get_json(credentials.GOOGLE_CLIENT)
    if not config:
        raise ProviderError("No Google OAuth client saved. Run: playlist-sync auth ytmusic")
    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    print("Waiting for you to finish signing in in your browser (up to 5 minutes; "
          "Ctrl+C to cancel)...", file=sys.stderr)
    try:
        creds = flow.run_local_server(port=0, open_browser=True, timeout_seconds=300,
                                      authorization_prompt_message="")
    except WSGITimeoutError as e:
        raise ProviderError(
            "Timed out waiting for Google sign-in. If Google showed 'Access blocked' or "
            "'has not completed the Google verification process', add your account under "
            "Google Auth Platform > Audience > Test users, then run this again."
        ) from e
    credentials.put(credentials.GOOGLE_TOKEN, creds.to_json())


def revoke() -> None:
    """Best-effort revocation on Google's side, so a logout is a real logout."""
    token = credentials.get_json(credentials.GOOGLE_TOKEN)
    if token and token.get("refresh_token"):
        with contextlib.suppress(httpx.HTTPError):
            httpx.post("https://oauth2.googleapis.com/revoke",
                       params={"token": token["refresh_token"]}, timeout=10)


class YouTubeDataAPI:
    def __init__(self):
        self._creds = None
        self._http = httpx.Client(timeout=30)

    def _token(self) -> str:
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        if self._creds is None:
            info = credentials.get_json(credentials.GOOGLE_TOKEN)
            if not info:
                raise ProviderError("Not logged in to Google. Run: playlist-sync auth ytmusic")
            self._creds = Credentials.from_authorized_user_info(info, SCOPES)
        if not self._creds.valid:
            try:
                self._creds.refresh(Request())
            except RefreshError as e:
                raise ProviderError(
                    "Google login expired or was revoked. Run: playlist-sync auth ytmusic. "
                    "If this happens every week, set your Google OAuth app's publishing "
                    "status to 'In production' (see README)."
                ) from e
            credentials.put(credentials.GOOGLE_TOKEN, self._creds.to_json())
        return self._creds.token

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = self._http.request(method, f"{API}{path}",
                                  headers={"Authorization": f"Bearer {self._token()}"}, **kwargs)
        if resp.status_code >= 400:
            try:
                reason = resp.json()["error"]["errors"][0]["reason"]
            except (ValueError, KeyError, IndexError):
                reason = ""
            raise _ApiError(resp.status_code, reason, resp.text[:200])
        return resp.json() if resp.content else {}

    def channel_title(self) -> str | None:
        """The signed-in account's YouTube channel name, or None if it has no channel."""
        try:
            data = self._request("GET", "/channels", params={"part": "snippet", "mine": "true"})
        except _ApiError as e:
            raise ProviderError(e.user_message()) from e
        items = data.get("items") or []
        return items[0]["snippet"]["title"] if items else None

    def create_playlist(self, name: str, description: str, public: bool) -> str:
        try:
            data = self._request("POST", "/playlists", params={"part": "snippet,status"}, json={
                "snippet": {"title": name, "description": description[:5000]},
                "status": {"privacyStatus": "public" if public else "private"},
            })
        except _ApiError as e:
            raise ProviderError(e.user_message()) from e
        return data["id"]

    def add_tracks(self, playlist_id: str, video_ids: list[str]) -> None:
        done: list[str] = []
        for video_id in video_ids:
            try:
                self._request("POST", "/playlistItems", params={"part": "snippet"}, json={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                })
            except _ApiError as e:
                if e.status == 404:
                    # Some songs can't be added through the API; skip, don't block the rest.
                    print(f"warning: YouTube wouldn't add video {video_id}; skipped.",
                          file=sys.stderr)
                else:
                    raise PartialWriteError(e.user_message(), done) from e
            done.append(video_id)

    def remove_tracks(self, playlist_id: str, video_ids: list[str]) -> None:
        wanted = set(video_ids)
        item_ids: list[str] = []
        page_token = None
        while True:
            data = self._request("GET", "/playlistItems", params={
                "part": "snippet", "playlistId": playlist_id, "maxResults": 50,
                **({"pageToken": page_token} if page_token else {}),
            })
            for item in data.get("items", []):
                if item["snippet"]["resourceId"].get("videoId") in wanted:
                    item_ids.append(item["id"])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        for item_id in item_ids:
            try:
                self._request("DELETE", "/playlistItems", params={"id": item_id})
            except _ApiError as e:
                raise ProviderError(e.user_message()) from e


class _ApiError(Exception):
    def __init__(self, status: int, reason: str, body: str):
        super().__init__(f"YouTube API {status} {reason}: {body}")
        self.status, self.reason = status, reason

    def user_message(self) -> str:
        if self.reason in ("accessNotConfigured", "SERVICE_DISABLED"):
            return ("The YouTube Data API v3 isn't enabled in your Google Cloud project. "
                    "Enable it under APIs & Services > Library, wait 2-3 minutes, and try "
                    "again.")
        if self.reason == "youtubeSignupRequired":
            return ("This Google account has no YouTube channel, which YouTube requires for "
                    "creating playlists. Create one at https://www.youtube.com/create_channel")
        if self.reason == "quotaExceeded":
            return ("YouTube's daily API quota is used up (about 200 track adds/day). "
                    "Progress is saved; run sync again tomorrow to continue.")
        return str(self)
