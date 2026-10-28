from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Track:
    """A track as seen by one service. Only `title` and `artists` are guaranteed."""

    title: str
    artists: tuple[str, ...]
    album: str | None = None
    duration_ms: int | None = None
    isrc: str | None = None
    # The track's ID on the service it came from (Spotify URI, YouTube videoId, ...).
    service_id: str | None = None

    @property
    def display(self) -> str:
        return f"{', '.join(self.artists)} - {self.title}"


@dataclass
class Playlist:
    service: str
    id: str
    name: str
    description: str = ""
    tracks: list[Track] = field(default_factory=list)
    # Set when the service only let us see part of the playlist.
    truncated: bool = False


@dataclass
class Link:
    """A source playlist mirrored into a target playlist."""

    id: int | None
    source_service: str
    source_id: str
    target_service: str
    target_id: str | None
    name: str
    last_synced_at: str | None = None
