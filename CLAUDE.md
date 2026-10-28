# playlist-sync

Open-source Python CLI to copy/sync public playlists across Spotify, YouTube Music and Amazon Music. Portfolio project.

- Setup: `python3 -m venv .venv && .venv/bin/pip install -e .`
- Code in `src/`, tests in `tests/` (pytest), lint with ruff.
- Spotify Feb 2026 API rules: Dev Mode needs Premium, 5 users max; only owned playlists readable, so other public playlists are read via the embed page; `/items` replaces `/tracks`; no ISRC.
- Amazon Music: API is invite-only and the web player blocks headless browsers, so reading goes through a bookmarklet (`src/playlist_sync/amazon/exporter.js`) that exports the visible playlist to CSV in the user's own browser; `providers/csvfile.py` imports it. Amazon page uses React Native Web (generated class names): find rows via `/albums/` and `/artists/` links, not CSS classes. The list is virtualized and only loads while the tab is visible.
