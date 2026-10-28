import pytest

from playlist_sync.models import Playlist, Track
from playlist_sync.providers.base import PartialWriteError, Provider
from playlist_sync.store import Store
from playlist_sync.sync import copy_playlist, sync_link


def t(title, artist, sid):
    return Track(title, (artist,), duration_ms=200_000, service_id=sid)


class FakeSource(Provider):
    name = "src"

    def __init__(self, tracks):
        self.tracks = tracks

    @staticmethod
    def parse_playlist_id(url):
        return "p1"

    def read_playlist(self, playlist_id):
        return Playlist(self.name, playlist_id, "Road Trip", tracks=list(self.tracks))

    def search_queries(self, track): ...
    def search(self, query): ...
    def create_playlist(self, name, description, public): ...
    def add_tracks(self, playlist_id, track_ids): ...
    def remove_tracks(self, playlist_id, track_ids): ...


class FakeTarget(Provider):
    name = "dst"

    def __init__(self, catalog):
        self.catalog = catalog
        self.playlists: dict[str, list[str]] = {}
        self.searches = 0

    @staticmethod
    def parse_playlist_id(url):
        return None

    def read_playlist(self, playlist_id): ...

    def search_queries(self, track):
        return [track.title]

    def search(self, query):
        self.searches += 1
        return [c for c in self.catalog if c.title == query]

    def create_playlist(self, name, description, public):
        self.playlists[name] = []
        return name

    def add_tracks(self, playlist_id, track_ids):
        self.playlists[playlist_id].extend(track_ids)

    def remove_tracks(self, playlist_id, track_ids):
        self.playlists[playlist_id] = [x for x in self.playlists[playlist_id]
                                       if x not in track_ids]


CATALOG = [t("One", "A", "d1"), t("Two", "B", "d2"), t("Three", "C", "d3")]


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "state.db")


def test_copy_creates_playlist_and_reports_unmatched(store):
    src = FakeSource([t("One", "A", "s1"), t("Two", "B", "s2"), t("Missing", "Z", "s9")])
    dst = FakeTarget(CATALOG)
    link, report = copy_playlist(src, "p1", "url", dst, store)

    assert dst.playlists["Road Trip"] == ["d1", "d2"]
    assert [x.title for x in report.unmatched] == ["Missing"]
    assert store.unmatched(link.id) == ["Z - Missing"]


def test_resync_only_adds_new_tracks_and_skips_known_misses(store):
    src = FakeSource([t("One", "A", "s1"), t("Missing", "Z", "s9")])
    dst = FakeTarget(CATALOG)
    link, _ = copy_playlist(src, "p1", "url", dst, store)
    searches_after_copy = dst.searches

    src.tracks.append(t("Three", "C", "s3"))
    report = sync_link(link, src, dst, store)

    assert dst.playlists["Road Trip"] == ["d1", "d3"]
    assert [x.title for x in report.added] == ["Three"]
    assert report.unchanged == 1
    assert dst.searches == searches_after_copy + 1  # Only the new track was searched.


def test_remove_missing(store):
    src = FakeSource([t("One", "A", "s1"), t("Two", "B", "s2")])
    dst = FakeTarget(CATALOG)
    link, _ = copy_playlist(src, "p1", "url", dst, store)

    src.tracks.pop(0)
    sync_link(link, src, dst, store)  # Default: keep removed tracks.
    assert dst.playlists["Road Trip"] == ["d1", "d2"]

    report = sync_link(link, src, dst, store, remove_missing=True)
    assert report.removed == ["d1"]
    assert dst.playlists["Road Trip"] == ["d2"]


def test_user_removed_track_is_not_readded(store):
    src = FakeSource([t("One", "A", "s1"), t("Two", "B", "s2")])
    dst = FakeTarget(CATALOG)
    link, _ = copy_playlist(src, "p1", "url", dst, store)

    dst.playlists["Road Trip"].remove("d1")  # The user deleted it by hand.
    sync_link(link, src, dst, store)
    assert dst.playlists["Road Trip"] == ["d2"]


def test_dry_run_changes_nothing(store):
    src = FakeSource([t("One", "A", "s1")])
    dst = FakeTarget(CATALOG)
    _, report = copy_playlist(src, "p1", "url", dst, store, dry_run=True)

    assert [x.title for x in report.added] == ["One"]
    assert dst.playlists == {}
    assert store.links() == []


def test_copy_twice_reuses_link(store):
    src = FakeSource([t("One", "A", "s1")])
    dst = FakeTarget(CATALOG)
    first, _ = copy_playlist(src, "p1", "url", dst, store)
    second, report = copy_playlist(src, "p1", "url", dst, store)

    assert first.id == second.id
    assert len(dst.playlists) == 1
    assert report.added == []


class QuotaTarget(FakeTarget):
    """Adds `limit` tracks, then fails like YouTube does when the daily quota runs out."""

    def __init__(self, catalog, limit):
        super().__init__(catalog)
        self.limit = limit

    def add_tracks(self, playlist_id, track_ids):
        done = []
        for tid in track_ids:
            if self.limit == 0:
                raise PartialWriteError("quota", done)
            self.playlists[playlist_id].append(tid)
            done.append(tid)
            self.limit -= 1


def test_partial_add_resumes_without_duplicates(store):
    src = FakeSource([t("One", "A", "s1"), t("Two", "B", "s2"), t("Three", "C", "s3")])
    dst = QuotaTarget(CATALOG, limit=1)
    link, report = copy_playlist(src, "p1", "url", dst, store)

    assert report.error == "quota"
    assert [x.title for x in report.added] == ["One"]
    assert store.get_link(link.id).last_synced_at is None

    dst.limit = 10  # Quota resets the next day.
    report = sync_link(link, src, dst, store)
    assert report.error is None
    assert dst.playlists["Road Trip"] == ["d1", "d2", "d3"]
