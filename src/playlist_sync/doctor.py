"""`playlist-sync doctor`: show what's configured and whether each login actually works."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

from . import credentials

OK, FAIL, SKIP = "✓", "✗", "–"


def run_checks(echo: Callable[[str], None]) -> bool:
    """Print a checklist. Returns False if anything that's configured is broken."""
    healthy = True

    def line(status: str, label: str, detail: str = "") -> None:
        nonlocal healthy
        healthy &= status != FAIL
        echo(f"  {status} {label}" + (f": {detail}" if detail else ""))

    echo("General")
    py = sys.version_info
    line(OK if py >= (3, 11) else FAIL, "Python", f"{py.major}.{py.minor}.{py.micro}")
    from .store import Store, home_dir

    line(OK, "State directory", str(home_dir()))
    line(OK, "Linked playlists", str(len(Store().links())))
    line(OK, "Login storage", credentials.backend_name())

    echo("\nSpotify")
    _check_spotify(line)

    echo("\nYouTube Music")
    _check_ytmusic(line)

    echo("\nAmazon Music")
    line(SKIP, "Not supported yet", "Amazon's API is invite-only")

    echo("\n" + ("All good." if healthy else "Some checks failed; see above."))
    return healthy


def _check_spotify(line) -> None:
    from .providers import spotify

    line(OK, "Read public playlists", "no login needed")
    if not spotify.client_id():
        line(SKIP, "Login", "not set up; run `playlist-sync auth spotify` to copy to Spotify")
        return
    mode = "classic (client secret)" if os.environ.get("SPOTIFY_CLIENT_SECRET") else "PKCE"
    line(OK, "Client ID", f"saved ({mode})")
    if not spotify.is_logged_in():
        line(FAIL, "Login", "Client ID saved but not logged in; run `playlist-sync auth spotify`")
        return
    try:
        me = spotify.SpotifyProvider()._request("GET", "/me")
        line(OK, "Login", f"working as {me.get('display_name') or me.get('id')}")
    except Exception as e:
        line(FAIL, "Login", f"{e} (if this is a 403, add yourself under User Management in "
                            "the Spotify dashboard)")


def _check_ytmusic(line) -> None:
    from .providers import youtube_api
    from .providers.ytmusic import YTMusicProvider, browser_client, has_browser_login

    try:
        YTMusicProvider().search("test")
        line(OK, "Read public playlists", "no login needed")
    except Exception as e:
        line(FAIL, "Read public playlists", str(e))

    if youtube_api.is_logged_in():
        try:
            title = youtube_api.YouTubeDataAPI().channel_title()
            if title:
                line(OK, "Google login", f"working as {title}")
            else:
                line(FAIL, "Google login", "signed in, but this account has no YouTube "
                     "channel, which YouTube requires for creating playlists. Create one at "
                     "https://www.youtube.com/create_channel, then re-run doctor")
        except Exception as e:
            line(FAIL, "Google login", str(e))
    elif has_browser_login():
        try:
            info = browser_client().get_account_info()
            line(OK, "Browser login", f"working as {info.get('accountName', '?')}")
        except Exception as e:
            line(FAIL, "Browser login", f"{e}; the cookie may have expired. Run "
                                        "`playlist-sync auth ytmusic --browser` again")
    else:
        line(SKIP, "Login", "not set up; run `playlist-sync auth ytmusic` to copy to YT Music")
