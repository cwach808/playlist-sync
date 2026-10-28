from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Annotated

import typer

from . import credentials
from .matching import DEFAULT_THRESHOLD
from .models import Track
from .providers import PROVIDERS, ProviderError, get_provider, parse_url, playlist_url
from .store import Store, home_dir
from .sync import SyncReport, copy_playlist, sync_link

app = typer.Typer(help="Copy public playlists between streaming services and keep them synced.",
                  no_args_is_help=True)
auth_app = typer.Typer(help="Connect your streaming accounts.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")


@app.callback()
def main(
    no_save: Annotated[bool, typer.Option(
        "--no-save", help="Keep logins in memory for this run only; nothing is stored.")] = False,
):
    credentials.set_session_only(no_save)

Threshold = Annotated[float, typer.Option(
    min=0.0, max=1.0, help="Match confidence required (0-1). Lower = more matches, more mistakes."
)]
DryRun = Annotated[bool, typer.Option("--dry-run", help="Show what would happen; change nothing.")]


def _progress():
    """Print each track as it's matched, so long runs don't look frozen."""
    count = 0

    def show(track: Track) -> None:
        nonlocal count
        count += 1
        typer.echo(f"  [{count}] matching {track.display}", err=True)

    return show


def _print_report(report: SyncReport, verbose: bool, dry_run: bool = False) -> None:
    pl = report.playlist
    would = "would be " if dry_run else ""
    if dry_run:
        typer.secho("\nDRY RUN: preview only. Nothing was created or changed.",
                    fg="yellow", bold=True)
    typer.echo(f"\n{pl.name!r}: {len(pl.tracks)} tracks in source")
    if pl.truncated:
        typer.secho("  note: the source service may not have returned every track.",
                    fg="yellow")
    typer.secho(f"  + {len(report.added)} {would}added", fg="green")
    if report.removed:
        typer.secho(f"  - {len(report.removed)} {would}removed", fg="red")
    typer.echo(f"  = {report.unchanged} already present")
    if report.unmatched:
        typer.secho(f"  ? {len(report.unmatched)} couldn't be matched", fg="yellow")
        if verbose:
            for t in report.unmatched:
                typer.echo(f"      {t.display}")
    if report.uncertain:
        typer.secho(f"  ~ {len(report.uncertain)} lower-confidence matches; worth a look:",
                    fg="cyan")
        for src, match, score in report.uncertain:
            typer.echo(f"      {src.display}\n        -> {match.display}  ({score:.2f})")
    if report.error:
        typer.secho(f"  ! stopped early: {report.error}", fg="red")


def _fail(e: Exception) -> None:
    typer.secho(f"Error: {e}", fg="red", err=True)
    raise typer.Exit(1)


def _expand_wildcards(sources: list[str]) -> list[str]:
    """Expand `*.csv` ourselves when the shell didn't (e.g. it was inside quotes)."""
    out: list[str] = []
    for src in sources:
        if "://" not in src and any(c in src for c in "*?["):
            matches = sorted(glob.glob(os.path.expanduser(src)))
            if not matches:
                _fail(ValueError(f"No files match {src}"))
            out.extend(matches)
        else:
            out.append(src)
    return out


@app.command()
def copy(
    sources: Annotated[list[str], typer.Argument(
        help="Playlist URLs (Spotify, YouTube Music) or CSV files. Give several to copy "
             "them all.", show_default=False)],
    to: Annotated[str, typer.Option("--to", help=f"Target service: {', '.join(PROVIDERS)}")],
    name: Annotated[str | None, typer.Option(
        help="Name for the new playlist (only when copying one).")] = None,
    public: Annotated[bool, typer.Option(help="Make the new playlists public.")] = False,
    threshold: Threshold = DEFAULT_THRESHOLD,
    dry_run: DryRun = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False,
):
    """Copy playlists to another service and remember them for `sync`."""
    sources = _expand_wildcards(sources)
    if name and len(sources) > 1:
        _fail(ValueError("--name only works when copying a single playlist."))
    store = Store()
    failures = 0
    for i, url in enumerate(sources, 1):
        if len(sources) > 1:
            typer.secho(f"\n[{i}/{len(sources)}] {url}", bold=True)
        try:
            source_name, source_id = parse_url(url)
            if source_name == to:
                raise ProviderError("Source and target are the same service.")
            source, target = get_provider(source_name), get_provider(to)
            # Don't put local file paths (which include your username) in playlist descriptions.
            shown = Path(source_id).name if source_name == "csv" else url
            link, report = copy_playlist(
                source, source_id, shown, target, store, name=name, public=public,
                dry_run=dry_run, threshold=threshold, on_track=_progress(),
            )
        except ProviderError as e:
            failures += 1
            typer.secho(f"Error: {e}", fg="red", err=True)
            continue
        _print_report(report, verbose=True, dry_run=dry_run)
        failures += bool(report.error)
        if not dry_run:
            if url_ := playlist_url(link.target_service, link.target_id):
                typer.echo(f"Open it: {url_}")
            if not report.error:
                typer.echo(f"Linked as #{link.id}.")
    if dry_run:
        typer.secho("\nTo do it for real, run the same command without --dry-run.", bold=True)
    if not dry_run and failures < len(sources):
        typer.echo("\nRun `playlist-sync sync` later to pick up changes.")
    if failures:
        if len(sources) > 1:
            typer.secho(f"\n{failures} of {len(sources)} failed; see errors above. Re-running "
                        "the same command skips finished ones and retries the rest.",
                        fg="red", err=True)
        raise typer.Exit(1)


@app.command("amazon-export")
def amazon_export():
    """Open the Amazon Music exporter (a bookmark that saves playlists as CSV)."""
    import webbrowser

    from .amazon import write_install_page

    path = write_install_page(home_dir())
    typer.echo(f"Opening {path}")
    typer.echo("Drag the green button to your bookmarks bar, then follow the steps on the page.")
    webbrowser.open(path.as_uri())


@app.command()
def sync(
    link_id: Annotated[int | None, typer.Argument(help="Only sync this link (see `list`).")] = None,
    remove_missing: Annotated[bool, typer.Option(
        help="Also remove tracks that were deleted from the source.")] = False,
    retry_unmatched: Annotated[bool, typer.Option(
        help="Search again for tracks that previously had no match.")] = False,
    threshold: Threshold = DEFAULT_THRESHOLD,
    dry_run: DryRun = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False,
):
    """Bring linked playlists up to date with their sources."""
    store = Store()
    links = store.links() if link_id is None else [store.get_link(link_id)]
    if not links or links == [None]:
        _fail(ValueError("Nothing to sync. Use `playlist-sync copy` first."))
    failures = 0
    for link in links:
        try:
            report = sync_link(
                link, get_provider(link.source_service), get_provider(link.target_service),
                store, remove_missing=remove_missing, retry_unmatched=retry_unmatched,
                dry_run=dry_run, threshold=threshold, on_track=_progress(),
            )
            _print_report(report, verbose, dry_run=dry_run)
            failures += bool(report.error)
        except ProviderError as e:
            failures += 1
            typer.secho(f"\n#{link.id} {link.name}: {e}", fg="red", err=True)
    if failures:
        raise typer.Exit(1)


@app.command("list")
def list_links():
    """Show linked playlists."""
    links = Store().links()
    if not links:
        typer.echo("No linked playlists yet.")
    for link in links:
        synced = link.last_synced_at or "never"
        typer.echo(f"#{link.id}  {link.name}  ({link.source_service} -> {link.target_service}, "
                   f"last synced {synced})")
        if url_ := playlist_url(link.target_service, link.target_id):
            typer.echo(f"     {url_}")


@app.command()
def unmatched(link_id: int):
    """List tracks that couldn't be found on the target service."""
    for display in Store().unmatched(link_id):
        typer.echo(display)


@app.command()
def unlink(link_id: int):
    """Stop syncing a playlist. The copied playlist itself is left alone."""
    if not Store().delete_link(link_id):
        _fail(ValueError(f"No link #{link_id}."))
    typer.echo(f"Unlinked #{link_id}.")


@auth_app.command("spotify")
def auth_spotify(
    client_id: Annotated[str | None, typer.Option(
        help="Your Spotify app's Client ID. Prompted for if not saved yet.")] = None,
):
    """Log in to Spotify in your browser. Only your app's Client ID is needed."""
    from .providers import spotify

    if not client_id and not spotify.client_id():
        typer.echo("Find your Client ID at https://developer.spotify.com/dashboard "
                   "(your app > Settings). See README: 'Spotify setup'.")
        client_id = typer.prompt("Spotify Client ID")
    try:
        typer.echo("Opening your browser to approve access...")
        spotify.login(client_id)
    except Exception as e:
        _fail(e)
    typer.secho(f"Spotify connected. Login saved to: {credentials.backend_name()}", fg="green")


@auth_app.command("ytmusic")
def auth_ytmusic(
    client_file: Annotated[str | None, typer.Option(
        help="OAuth client JSON downloaded from Google Cloud Console.")] = None,
    browser: Annotated[bool, typer.Option(
        "--browser", help="Advanced: paste browser request headers instead of signing in "
        "with Google. No daily quota, but the saved cookie grants full account access.")] = False,
):
    """Log in to YouTube Music (Google sign-in in your browser by default)."""
    from .providers import youtube_api

    if browser:
        import ytmusicapi

        typer.echo(
            "1. Open https://music.youtube.com in a browser where you're logged in.\n"
            "2. Open DevTools > Network, filter for 'browse', and click a matching request.\n"
            "3. Copy its request headers, paste them below, then press Ctrl-D.\n"
            "Full guide: https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html\n"
        )
        credentials.put(credentials.YTMUSIC_BROWSER, ytmusicapi.setup())
        typer.secho(f"YouTube Music connected. Saved to: {credentials.backend_name()}",
                    fg="green")
        return

    try:
        config = None
        if client_file:
            config = youtube_api.load_client_file(client_file)
        elif not credentials.get(credentials.GOOGLE_CLIENT):
            typer.echo("You need a Google OAuth client file first. See README: "
                       "'YouTube Music setup'.")
            config = youtube_api.load_client_file(
                typer.prompt("Path to the downloaded client JSON").strip().strip("'\"")
            )
        typer.echo("Opening your browser to sign in with Google...")
        youtube_api.login(config)
    except (OSError, ValueError, ProviderError) as e:
        _fail(e)
    typer.secho(f"YouTube Music connected. Login saved to: {credentials.backend_name()}",
                fg="green")
    if client_file:
        typer.echo(f"The client file has been saved securely; you can delete {client_file}.")


@auth_app.command("logout")
def auth_logout(
    service: Annotated[str, typer.Argument(help="spotify, ytmusic, or all")] = "all",
):
    """Delete saved logins (and revoke Google access)."""
    from .providers import youtube_api

    if service not in ("spotify", "ytmusic", "all"):
        _fail(ValueError("Choose spotify, ytmusic, or all."))
    if service in ("spotify", "all"):
        credentials.delete(credentials.SPOTIFY_TOKEN)
        credentials.delete(credentials.SPOTIFY_CLIENT_ID)
        typer.echo("Spotify logged out. To fully revoke, remove the app at "
                   "https://www.spotify.com/account/apps/")
    if service in ("ytmusic", "all"):
        youtube_api.revoke()
        for name in (credentials.GOOGLE_TOKEN, credentials.GOOGLE_CLIENT,
                     credentials.YTMUSIC_BROWSER):
            credentials.delete(name)
        typer.echo("YouTube Music logged out and Google access revoked.")


@auth_app.command("export")
def auth_export():
    """Print saved logins as env vars, for GitHub Actions secrets. Treat output as a password."""
    found = False
    for name in credentials.ALL:
        if value := credentials.get(name):
            found = True
            typer.echo(f"{credentials.env_var(name)}={value}")
    if not found:
        _fail(ValueError("No saved logins to export."))
    typer.secho("\nThese grant access to your accounts. Paste them into repository secrets "
                "and clear your terminal.", fg="yellow", err=True)


@app.command()
def doctor():
    """Check your setup and logins for each service."""
    from .doctor import run_checks

    ok = run_checks(typer.echo)
    raise typer.Exit(0 if ok else 1)


@app.command()
def where():
    """Print where sync state and logins are stored."""
    typer.echo(f"state:  {home_dir()}")
    typer.echo(f"logins: {credentials.backend_name()}")


if __name__ == "__main__":
    app()
