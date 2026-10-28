# Backlog

Known bugs and small improvements, newest first. Move items to GitHub Issues once the
repo is public.

## Bugs

### Spotify: new playlists come out public despite asking for private
- **Seen:** 2026-10-25 (playlists #1 and #3 are both `public: true`)
- `create_playlist` sends `"public": false` to `POST /me/playlists`, then, if the response
  says public, sends `PUT /playlists/{id}` with `{"public": false}`. The playlist is
  still public afterward.
- **To investigate (needs the user's OK to test on one of their playlists):** what the
  create response's `public` field says; whether the PUT returns an error that's being
  swallowed; and whether Spotify's Feb 2026 Dev Mode changes ignore the visibility
  setting. Add a test once the cause is known.
- **Workaround:** in Spotify, open the playlist, click **⋯**, then **Make private**.

### Amazon exporter: panel shows a stale count after leaving a playlist
- **Seen:** 2026-10-24
- **Steps:** run the exporter on a playlist, then press Back to return to the library.
- **Expected:** the panel hides or says "Open a playlist to export it."
- **Actual:** "collected 0 of 112 songs". The count resets, but the total still comes
  from the previous playlist.
- **Likely cause:** on a URL change, `collect()` resets `tracks` but keeps rendering.
  `expectedTotal()` searches the whole page text for "N SONGS", which can match leftover
  text from the previous view in the single-page app.
- **Fix idea:** only run on `/user-playlists/` and `/playlists/` paths, and show an idle
  message elsewhere. Read the total from the playlist header area, not the whole page.

### Amazon exporter: count can exceed the playlist's real size
- **Seen:** 2026-10-24
- **Steps:** export a playlist whose header says 100 songs.
- **Actual:** "collected 101 of 112". Both numbers are wrong: the total came from
  another playlist, and one extra row was counted.
- **Likely cause:** same stale-total issue as above. With the wrong total (112), the
  "song number can't exceed the total" guard doesn't catch the extra row. The extra row
  is probably a suggested song, or the "resume" row being slotted into a gap.
- **Fix idea:** fix the total first, then check the exported CSV for the extra row to
  see which one it is.
- **Workaround:** reload the page (Cmd+R) before exporting each playlist.

### Matching: bare "HQ"/"HD" suffix isn't stripped
- **Seen:** 2026-10-07 ("Jon Secada - Just Another Day HQ")
- Only bracketed noise like "(HQ)" is removed. Strip a trailing bare HQ/HD/4K too, and
  add a regression test.

## Improvements

- Security: the Amazon exporter writes song titles straight into the CSV. A title that
  starts with `=`, `+`, `-` or `@` could run as a formula if the user opens the file in
  Excel ("CSV injection", CWE-1236). Low risk: playlist-sync never runs formulas. Fix by
  prefixing such cells with `'` in the exporter and stripping it in `csvfile.py`.

- YouTube (Google sign-in): with a Testing-status OAuth app, logins expire every 7 days.
  Make `doctor` show the login's age and warn before it expires, so scheduled syncs don't
  fail silently.

- Amazon exporter: a "Done" sound or tab-title change, so users can switch tabs while
  it runs.
- Spotify: optionally save matches to Liked Songs instead of a playlist (needs the
  `user-library-modify` scope and the new `PUT /me/library` endpoint).
