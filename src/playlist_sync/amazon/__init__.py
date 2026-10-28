"""Amazon Music export via a bookmarklet, since Amazon has no public API.

The bookmarklet runs in the user's own browser on a playlist page they're viewing and
downloads a CSV, which `playlist-sync copy file.csv --to spotify` then imports.
"""

from __future__ import annotations

import html
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote


def bookmarklet_url() -> str:
    source = files(__package__).joinpath("exporter.js").read_text(encoding="utf-8")
    return "javascript:" + quote(source, safe="")


INSTALL_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Amazon Music exporter</title>
<style>
  :root {{ color-scheme: light dark; --bg:#fafafa; --fg:#111; --muted:#555; --card:#fff; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#111; --fg:#eee; --muted:#aaa; --card:#1c1c1c; }}
  }}
  body {{ background:var(--bg); color:var(--fg); margin:0;
         font:16px/1.55 -apple-system, system-ui, sans-serif; }}
  main {{ max-width:640px; margin:0 auto; padding:32px 16px; }}
  .card {{ background:var(--card); border-radius:12px; padding:20px; margin:20px 0; }}
  a.bm {{ display:inline-block; padding:10px 18px; border-radius:999px; background:#1ed760;
         color:#000; font-weight:600; text-decoration:none; cursor:grab; }}
  code {{ background:rgba(127,127,127,.15); padding:1px 5px; border-radius:4px; }}
  .muted {{ color:var(--muted); font-size:14px; }}
</style></head>
<body><main>
<h1>Amazon Music &rarr; CSV exporter</h1>
<p>Amazon Music has no public API, so this little bookmark reads the playlist you're
looking at and downloads it as a CSV file for <code>playlist-sync</code>.</p>

<div class="card">
<h2>1. Install (once)</h2>
<p>Show your bookmarks bar (<b>Cmd+Shift+B</b> on Mac, <b>Ctrl+Shift+B</b> on Windows),
then <b>drag this button onto it</b>:</p>
<p><a class="bm" href="{url}">Export to playlist-sync</a></p>
<p class="muted">Clicking it here does nothing; it only works on music.amazon.com.</p>
</div>

<div class="card">
<h2>2. Export a playlist</h2>
<ol>
<li>Open <a href="https://music.amazon.com/my/playlists">your playlists on Amazon Music</a>
and open one, e.g. <b>My Likes</b>.</li>
<li>Click <b>Export to playlist-sync</b> in your bookmarks bar.</li>
<li>Keep the tab in front while it scrolls and counts. When it says <b>Done</b>, click
<b>Download CSV</b>.</li>
</ol>
<p class="muted">Repeat for each playlist. Files land in your Downloads folder, named after
the playlist.</p>
</div>

<div class="card">
<h2>3. Copy to Spotify</h2>
<p>One playlist: <code>playlist-sync copy "~/Downloads/My Likes.csv" --to spotify</code></p>
<p>Many at once: <code>playlist-sync copy ~/Downloads/amazon/*.csv --to spotify</code></p>
<p class="muted">Add <code>--dry-run</code> first to preview matches.</p>
</div>

<p class="muted">Privacy: the bookmark only reads the page in your own browser. It doesn't
log in, call Amazon's private APIs, or send data anywhere.</p>
</main></body></html>
"""


def write_install_page(directory: Path) -> Path:
    path = directory / "amazon-exporter.html"
    path.write_text(INSTALL_PAGE.format(url=html.escape(bookmarklet_url(), quote=True)),
                    encoding="utf-8")
    return path
