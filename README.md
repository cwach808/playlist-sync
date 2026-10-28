<p align="center">
  <img src="assets/logo.svg" alt="playlist-sync logo" width="120">
</p>

# playlist-sync

[![ci](https://github.com/cwach808/playlist-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/cwach808/playlist-sync/actions/workflows/ci.yml)

Found a great playlist on a streaming service you don't use? `playlist-sync` copies it
to the one you do, then keeps it updated as the original changes.

```console
$ playlist-sync copy "https://music.youtube.com/playlist?list=PL..." --to spotify
'Late Night Jazz': 48 tracks in source
  + 45 added
  = 0 already present
  ? 3 couldn't be matched
      Bill Evans Trio - My Foolish Heart (Live at the Village Vanguard 1961, Take 2)
      ...
Linked as #1. Run `playlist-sync sync` to pick up future changes.

$ playlist-sync sync          # run weekly; only new tracks are searched and added
```

> **Disclaimer:** playlist-sync is an independent project, not affiliated with or
> endorsed by Spotify, Google/YouTube, or Amazon. Some features rely on unofficial
> methods (see [Platform constraints](#platform-constraints)) that may break or conflict
> with a service's terms. Use at your own risk.

## Supported services

| Service | Copy *from* | Copy *to* | How |
|---|---|---|---|
| Spotify | ✅ public playlists | ✅ | Official Web API + public embed page |
| YouTube Music | ✅ public playlists | ✅ | Official YouTube Data API + [`ytmusicapi`](https://github.com/sigma67/ytmusicapi) |
| Amazon Music | ✅ via [CSV export](#amazon-music-export-to-csv) | ❌ | Amazon's API is invite-only, so a bookmark exports playlists from your browser |
| CSV files | ✅ | – | Our Amazon exporter, [Exportify](https://exportify.app), TuneMyMusic, or your own list |

## How it works

1. **Read** the source playlist. No login is needed for public playlists.
2. **Match** each track on the target service. Services don't share IDs (Spotify
   stopped exposing ISRC codes to most apps in 2026, and YouTube never did), so matches
   come from fuzzy comparison of normalized titles, artists, and durations. Titles are
   cleaned of noise like `(Official Video)` or `- Remastered 2011`. Live, remix, acoustic,
   and other alternate versions are penalized so you get the studio track. You can tune
   the cutoff with `--threshold`.
3. **Remember** every match in a local SQLite database. Re-syncs only search for new
   tracks, never re-add a track you deleted from your copy, and pick up where they left
   off if a run is interrupted.

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/cwach808/playlist-sync && cd playlist-sync
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
playlist-sync doctor    # shows what's set up and what isn't
```

## Setup

You only need to connect the services you're copying **to**.

**No passwords or secrets go in config files.** You sign in through each service's own
page in your browser. The resulting tokens are stored in your OS keychain (macOS
Keychain, Windows Credential Manager, or Linux Secret Service). If no keychain is
available, they go in a file only your user can read, and you'll get a warning. Use
`--no-save` on any command to keep logins in memory for that run only.

### Spotify setup (about 5 minutes)

Spotify requires every app that uses its API to be registered, so you create your own
free "app" once. The app owner needs **Spotify Premium** (a Spotify rule since
February 2026).

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and
   log in. Accept the Developer Terms the first time.
2. Click **Create app** and fill in:
   - **App name / description:** anything, e.g. "My playlist-sync".
   - **Redirect URI:** `http://127.0.0.1:8888/callback`. It must be `127.0.0.1`, not
     `localhost`.
   - **Which API/SDKs:** check **Web API**.
3. Save, open the app's **Settings**, and copy the **Client ID**. You don't need the
   Client Secret.
4. Run:

   ```bash
   playlist-sync auth spotify     # asks for the Client ID, then opens your browser
   ```

**Sharing with family or friends:** the app owner is allowed automatically. Add up to
4 more people under your app's **User Management** tab (their name plus the email on
their Spotify account). Anyone not listed gets a 403 error. Development Mode apps are
capped at 5 users, so each person outside that circle should create their own app.

### YouTube Music setup (about 10 minutes)

Writing to YouTube uses Google's official API, which needs a free Google Cloud project.

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create a
   project, e.g. "playlist-sync".
2. Go to **APIs & Services → Library**, search for **YouTube Data API v3**, and click
   **Enable**.
3. Go to **Google Auth Platform** (formerly "OAuth consent screen") and click
   **Get started**:
   - **App name:** anything. **Support email:** yours.
   - **Audience:** External.
   - Finish the wizard.
4. Under **Audience**, add your Google account under **Test users**. Then try
   **Publish app** to move to **In production**.
   - If **Publish app** is grayed out, upload an **app logo** on the **Branding** page (a
     square PNG of at least 120×120). Google doesn't mark it as required, but won't
     publish without it.
   - As of October 2026, publishing personal apps is unreliable: the status may stay at
     **Testing**. That's OK. Everything works in Testing, but Google expires your login
     every 7 days. When `sync` reports that, run `playlist-sync auth ytmusic` again (about
     30 seconds).
   - When you sign in, Google shows a "Google hasn't verified this app" screen. Click
     **Advanced → Go to playlist-sync** to continue.
5. Go to **Clients → Create client**, choose **Application type: Desktop app**, create
   it, and **download the JSON**.
6. Run:

   ```bash
   playlist-sync auth ytmusic --client-file ~/Downloads/client_secret_XXXX.json
   ```

   This opens your browser to sign in with Google. The client file is stored securely,
   so you can delete the download afterward.

**Daily limit:** Google's free quota allows about **200 track adds per day**. A big
first copy may take more than one day. Progress is saved, so just run `sync` again
tomorrow. Searching doesn't count against the quota.

<details>
<summary><b>Alternative: browser login (no Google Cloud project, no daily limit)</b></summary>

`ytmusicapi` can use your browser session instead:

1. Open [music.youtube.com](https://music.youtube.com) in a browser where you're
   logged in.
2. Open DevTools (**Cmd+Opt+I** / **Ctrl+Shift+I**) → **Network** tab.
3. Click around (e.g. **Library**) and type `browse` in the filter box.
4. Click a `browse` request with status 200 and copy its **request headers**:
   - **Firefox:** right-click → **Copy Value → Copy Request Headers**.
   - **Chrome:** in **Headers**, turn on **Raw** under *Request Headers* and copy it.
5. Run `playlist-sync auth ytmusic --browser`, paste, and press **Ctrl-D**.

⚠️ This saves your browser **session cookie**, which grants full access to your
YouTube/Google session. It stops working if you log out of that browser session.
([ytmusicapi guide](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html))
</details>

### Amazon Music: export to CSV

Amazon has no public API, and its web player blocks automated browsers. So
playlist-sync reads Amazon playlists the way you do: from the page in your own browser.

```bash
playlist-sync amazon-export
```

This opens a page with an **Export to playlist-sync** button. Drag it to your bookmarks
bar once. Then, for each playlist:

1. Open it on [music.amazon.com](https://music.amazon.com/my/playlists). Your liked
   songs are the **My Likes** playlist.
2. Click the bookmark. It scrolls through the list and counts the songs. Keep the tab in
   front while it works.
3. When it says **Done**, click **Download CSV**.

Then copy one playlist or all of them at once:

```bash
playlist-sync copy ~/Downloads/amazon/*.csv --to spotify --dry-run   # preview
playlist-sync copy ~/Downloads/amazon/*.csv --to spotify
```

The bookmark only reads what's on your screen. It never sees your Amazon password,
doesn't call Amazon's private APIs, and sends nothing anywhere. Because there's no API,
Amazon playlists can't sync automatically: to pick up changes, re-export to the same file
and run `playlist-sync sync`.

CSV import works with other exporters too. Any CSV with a title column and an artist
column will do.

### Managing logins

```bash
playlist-sync doctor                 # test each login
playlist-sync where                  # where state and logins are stored
playlist-sync auth logout [spotify|ytmusic|all]
```

`logout` deletes stored tokens and revokes Google access. To fully revoke Spotify,
also remove the app at [spotify.com/account/apps](https://www.spotify.com/account/apps/).

## Usage

```bash
playlist-sync copy URL_OR_CSV... --to spotify [--name "My copy"] [--public] [--dry-run]
playlist-sync sync [LINK_ID] [--remove-missing] [--retry-unmatched] [--dry-run] [-v]
playlist-sync list                 # linked playlists
playlist-sync unmatched LINK_ID    # tracks that couldn't be found
playlist-sync unlink LINK_ID       # stop syncing; your copy is left alone
```

**File and folder names with spaces:** put quotes around the path, or the terminal splits
it into several arguments at each space:

```bash
playlist-sync copy "~/Downloads/Amazon Music/My Likes.csv" --to spotify    # ✅
playlist-sync copy ~/Downloads/"Amazon Music"/*.csv --to spotify            # ✅
playlist-sync copy "~/Downloads/Amazon Music/*.csv" --to spotify            # ✅ (expanded for you)
playlist-sync copy ~/Downloads/Amazon Music/*.csv --to spotify              # ❌ no quotes
```

Tip: type the start of a name and press **Tab**. The terminal fills in the rest, quoting
or escaping spaces and emoji for you. You can also drag a file from Finder into the
terminal window to paste its path.

By default, `sync` only **adds** tracks. Pass `--remove-missing` to also remove tracks
that were removed from the source.

## Scheduling a weekly sync

**On your own machine (simplest):** add a cron entry with `crontab -e`:

```cron
0 9 * * 1  cd /path/to/playlist-sync && .venv/bin/playlist-sync sync >> ~/.playlist-sync/sync.log 2>&1
```

On macOS, the first scheduled run may ask once to allow Keychain access.

**On GitHub Actions (experimental):** see
[`examples/weekly-sync.yml`](examples/weekly-sync.yml). Runners have no keychain, so
logins are passed in as repository secrets, which you get from `playlist-sync auth export`.
Spotify refresh tokens from the Client-ID-only (PKCE) login are single-use, which
doesn't work when the runner can't save the new one. So for Actions, log in to Spotify
with your Client Secret set:

```bash
SPOTIFY_CLIENT_SECRET=... playlist-sync auth spotify
```

## Platform constraints

- **Spotify (Feb 2026 API rules):** Development Mode apps need the owner to have
  Premium, allow 5 users, and can only read the contents of playlists you own or
  collaborate on. To read other people's public playlists, playlist-sync uses Spotify's
  public embed page. This is unofficial and may not include every track of very long
  playlists.
- **YouTube Music:** reading and searching use `ytmusicapi`, an unofficial but widely
  used library. Writing uses the official YouTube Data API (or `ytmusicapi` if you chose
  browser login).
- **Amazon Music:** no public API (invite-only beta, closed to new developers as of 2026),
  and the web player rejects automated browsers. playlist-sync deliberately doesn't try to
  get around that; the bookmark exporter reads only what you're viewing.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

Each service is a `Provider` (`src/playlist_sync/providers/`) with read, search, create,
add, and remove methods. To add a service, implement the class and register it in
`providers/__init__.py`. Logins go through `credentials.py`. The sync engine is tested
against fake providers in `tests/test_sync.py`.

## Roadmap

- [x] Copy and incremental sync: YouTube Music ⇄ Spotify
- [x] Browser sign-in with keychain storage; `doctor` setup checks
- [x] Amazon Music → anywhere, via the CSV bookmark exporter
- [ ] Amazon Music as a target (needs Amazon's API to open up)
- [ ] Review screen for low-confidence matches
- [ ] Spotify editorial and algorithmic playlists (the embed reader partly works today)
- [ ] Web UI

## License

[MIT](LICENSE) © Christina Wachter

[Privacy policy](PRIVACY.md)
