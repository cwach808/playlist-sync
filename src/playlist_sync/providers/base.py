from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Playlist, Track


class ProviderError(Exception):
    """A user-facing problem talking to a service (bad URL, missing auth, API refusal)."""


class PartialWriteError(ProviderError):
    """Adding tracks failed partway through. `done` lists the IDs that were added."""

    def __init__(self, message: str, done: list[str]):
        super().__init__(message)
        self.done = done


class Provider(ABC):
    """One streaming service. Track IDs are whatever the service uses to add a track."""

    name: str

    @staticmethod
    @abstractmethod
    def parse_playlist_id(url: str) -> str | None:
        """Return the playlist ID if `url` points at this service, else None."""

    @abstractmethod
    def read_playlist(self, playlist_id: str) -> Playlist: ...

    @abstractmethod
    def search_queries(self, track: Track) -> list[str]:
        """Search strings to try, most specific first."""

    @abstractmethod
    def search(self, query: str) -> list[Track]: ...

    @abstractmethod
    def create_playlist(self, name: str, description: str, public: bool) -> str: ...

    @abstractmethod
    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        """Append tracks in order. Raise PartialWriteError if only some were added."""

    @abstractmethod
    def remove_tracks(self, playlist_id: str, track_ids: list[str]) -> None: ...


def chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
