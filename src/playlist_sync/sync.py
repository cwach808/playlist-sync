"""Copy a playlist to another service, then keep it updated incrementally."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .matching import CONFIDENT, DEFAULT_THRESHOLD, best_match, track_key
from .models import Link, Playlist, Track
from .providers import Provider
from .providers.base import PartialWriteError
from .store import Store

ATTRIBUTION = "Synced from {url} by playlist-sync."


@dataclass
class SyncReport:
    playlist: Playlist
    added: list[Track] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unmatched: list[Track] = field(default_factory=list)
    # Accepted but not certain: (source track, chosen match, score), worth a human look.
    uncertain: list[tuple[Track, Track, float]] = field(default_factory=list)
    unchanged: int = 0
    # Set when the run stopped early (e.g. the target's daily quota ran out).
    error: str | None = None


def find_match(
    track: Track, target: Provider, threshold: float = DEFAULT_THRESHOLD
) -> tuple[Track | None, float]:
    best: tuple[Track | None, float] = (None, 0.0)
    for query in target.search_queries(track):
        match, score = best_match(track, target.search(query), threshold)
        if match:
            return match, score
        best = max(best, (None, score), key=lambda b: b[1])
    return best


def sync_link(
    link: Link,
    source: Provider,
    target: Provider,
    store: Store,
    *,
    remove_missing: bool = False,
    retry_unmatched: bool = False,
    dry_run: bool = False,
    threshold: float = DEFAULT_THRESHOLD,
    on_track: Callable[[Track], None] | None = None,
    playlist: Playlist | None = None,
) -> SyncReport:
    playlist = playlist or source.read_playlist(link.source_id)
    report = SyncReport(playlist)
    existing = store.link_items(link.id) if link.id else {}
    present_targets = {t for t in existing.values() if t}
    to_add: list[str] = []
    # Matched tracks are only recorded once they're really in the target playlist, so an
    # interrupted run (quota, network) retries them next time instead of losing them.
    pending: list[tuple[str, str, Track]] = []
    seen_keys: set[str] = set()

    def record(key: str, target_id: str | None, track: Track) -> None:
        if not dry_run and link.id:
            store.set_link_item(link.id, key, target_id, track)

    for track in playlist.tracks:
        key = track_key(track)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        if existing.get(key):
            report.unchanged += 1
            continue
        if key in existing and not retry_unmatched:
            report.unmatched.append(track)
            continue

        if on_track:
            on_track(track)
        cached = None if retry_unmatched else store.cached_match(source.name, key, target.name)
        if cached is not None:
            target_id = cached[0]
        else:
            match, score = find_match(track, target, threshold)
            target_id = match.service_id if match else None
            if match and score < CONFIDENT:
                report.uncertain.append((track, match, score))
            if not dry_run:
                store.save_match(source.name, key, target.name, target_id, score)

        if not target_id:
            report.unmatched.append(track)
            record(key, None, track)
        elif target_id in present_targets:
            report.unchanged += 1  # Already there, or two source tracks share one match.
            if target_id in to_add:
                pending.append((key, target_id, track))
            else:
                record(key, target_id, track)
        else:
            to_add.append(target_id)
            present_targets.add(target_id)
            pending.append((key, target_id, track))
            report.added.append(track)

    gone = [k for k in existing if k not in seen_keys]
    if remove_missing and gone:
        still_wanted = {existing[k] for k in existing if k in seen_keys} | set(to_add)
        to_remove = list(dict.fromkeys(
            existing[k] for k in gone if existing[k] and existing[k] not in still_wanted
        ))
        report.removed = to_remove
        if not dry_run:
            if to_remove:
                target.remove_tracks(link.target_id, to_remove)
            for k in gone:
                store.remove_link_item(link.id, k)

    if dry_run:
        return report
    added_ids = set(to_add)
    try:
        if to_add:
            target.add_tracks(link.target_id, to_add)
    except PartialWriteError as e:
        # Tracks are added in order, so what got done is a prefix of `to_add`.
        added_ids = set(e.done)
        report.added = report.added[: len(e.done)]
        report.error = str(e)
    for key, target_id, track in pending:
        if target_id in added_ids:
            record(key, target_id, track)
    if report.error is None:
        store.mark_synced(link.id)
    return report


def copy_playlist(
    source: Provider,
    source_id: str,
    source_url: str,
    target: Provider,
    store: Store,
    *,
    name: str | None = None,
    public: bool = False,
    dry_run: bool = False,
    threshold: float = DEFAULT_THRESHOLD,
    on_track: Callable[[Track], None] | None = None,
) -> tuple[Link, SyncReport]:
    """Create a mirror of a playlist on `target` and remember the link for future syncs."""
    if existing := store.find_link(source.name, source_id, target.name):
        report = sync_link(existing, source, target, store, dry_run=dry_run,
                           threshold=threshold, on_track=on_track)
        return existing, report

    if dry_run:
        link = Link(None, source.name, source_id, target.name, None, name or "")
        return link, sync_link(link, source, target, store, dry_run=True,
                               threshold=threshold, on_track=on_track)

    playlist = source.read_playlist(source_id)
    title = name or playlist.name or "Synced playlist"
    target_id = target.create_playlist(title, ATTRIBUTION.format(url=source_url), public)
    link = store.add_link(Link(None, source.name, source_id, target.name, target_id, title))
    return link, sync_link(link, source, target, store, threshold=threshold, on_track=on_track,
                           playlist=playlist)
