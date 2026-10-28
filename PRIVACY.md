# Privacy Policy

_Last updated: October 24, 2026_

playlist-sync is an open-source command-line tool that runs entirely on your own
computer. It has no servers, no accounts, and no analytics. The maintainers never
receive or see your data.

## What playlist-sync accesses

When you connect a service, playlist-sync asks that service for permission to:

- **Spotify:** read and modify your playlists (`playlist-read-private`,
  `playlist-modify-private`, `playlist-modify-public`).
- **YouTube (Google):** manage your YouTube playlists
  (`https://www.googleapis.com/auth/youtube`). It uses this only to create playlists,
  add or remove songs in playlists it created, and show your channel name in
  `playlist-sync doctor`.

It also reads **public** playlists you point it at, and CSV files you export yourself
(for example with the Amazon Music exporter bookmark).

playlist-sync uses this access only to copy and sync the playlists you ask it to.

## What is stored, and where

Everything stays on your computer:

- **Login tokens** are stored in your operating system's keychain (macOS Keychain,
  Windows Credential Manager, or Linux Secret Service). If no keychain is available,
  they go in a file only your user account can read. With `--no-save`, nothing is
  stored.
- **Sync state** (which playlists are linked, and which songs matched) is stored in a
  local database in `~/.playlist-sync/`.

Your passwords are never seen or stored by playlist-sync: you sign in on Spotify's and
Google's own pages.

## What is shared

playlist-sync talks only to the services you connect (Spotify, Google/YouTube, and
YouTube Music for searching), and only to do what you asked. It does not send your
data to the maintainers or any third party, and it does not sell or share data.

The Amazon Music exporter bookmark runs only in your own browser tab, reads only the
playlist you're viewing, and saves a CSV to your computer. It sends nothing anywhere.

## Google API Services User Data Policy

playlist-sync's use of information received from Google APIs adheres to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements.

## Removing access and data

- Run `playlist-sync auth logout` to delete stored logins. This also revokes Google
  access.
- You can also revoke access at any time from
  [Google account permissions](https://myaccount.google.com/permissions) and
  [Spotify apps](https://www.spotify.com/account/apps/).
- Delete `~/.playlist-sync/` to remove all local sync data.

## Changes and contact

Changes to this policy are tracked in this repository's history. For questions, open
an issue on the project's GitHub repository.
