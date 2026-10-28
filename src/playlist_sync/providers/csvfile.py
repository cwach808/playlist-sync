"""CSV files as a playlist source.

Reads exports from our Amazon Music bookmarklet, Exportify, TuneMyMusic, and
hand-made lists. Only a title and artist column are required.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from ..models import Playlist, Track
from .base import Provider, ProviderError

# Accepted header names (lowercased) for each field, from the common exporters.
_COLUMNS = {
    "title": ("title", "track name", "track", "name", "song", "song name"),
    "artist": ("artist", "artists", "artist name", "artist name(s)", "artist names"),
    "album": ("album", "album name"),
    "duration": ("duration", "duration (ms)", "length", "time"),
    "isrc": ("isrc",),
}


# Exporters that list several artists separated by commas. Everything else, including our
# Amazon exporter, uses ";" so names like "Earth, Wind & Fire" stay in one piece.
_COMMA_SEPARATED_HEADERS = ("artist name(s)", "artists", "artist names")


def split_artists(value: str, sep: str) -> tuple[str, ...]:
    return tuple(a.strip() for a in value.split(sep) if a.strip())


def parse_duration(value: str) -> int | None:
    """'3:47', '1:02:03', or milliseconds ('227000') -> milliseconds."""
    value = (value or "").strip()
    if not value:
        return None
    if value.isdigit():
        n = int(value)
        return n if n > 10_000 else n * 1000  # Big numbers are ms, small ones seconds.
    parts = value.split(":")
    if all(p.isdigit() for p in parts) and 2 <= len(parts) <= 3:
        seconds = 0
        for p in parts:
            seconds = seconds * 60 + int(p)
        return seconds * 1000
    return None


class CsvFileProvider(Provider):
    name = "csv"

    @staticmethod
    def parse_playlist_id(url: str) -> str | None:
        if not url.lower().endswith(".csv"):
            return None
        return str(Path(url).expanduser().resolve())

    def read_playlist(self, playlist_id: str) -> Playlist:
        path = Path(playlist_id)
        if not path.exists():
            raise ProviderError(f"CSV file not found: {path}. If you re-exported it, save it "
                                "to the same place so sync can find it.")
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            columns = _map_columns(reader.fieldnames or [])
            if "title" not in columns or "artist" not in columns:
                raise ProviderError(f"{path.name} needs a title column and an artist column "
                                    f"(found: {', '.join(reader.fieldnames or [])})")
            sep = "," if columns["artist"].strip().lower() in _COMMA_SEPARATED_HEADERS else ";"
            tracks = []
            for row in reader:
                title = (row.get(columns["title"]) or "").strip()
                if not title:
                    continue
                tracks.append(Track(
                    title=title,
                    artists=split_artists(row[columns["artist"]] or "", sep),
                    album=(row.get(columns.get("album", "")) or "").strip() or None,
                    duration_ms=parse_duration(row.get(columns.get("duration", "")) or ""),
                    isrc=(row.get(columns.get("isrc", "")) or "").strip() or None,
                ))
        # Browsers name repeat downloads "My Likes (1).csv"; that's still "My Likes".
        name = re.sub(r"\s\(\d+\)$", "", path.stem)
        return Playlist(self.name, playlist_id, name, tracks=tracks)

    def search_queries(self, track: Track) -> list[str]:
        raise ProviderError("CSV files can only be copied from, not to.")

    def search(self, query: str) -> list[Track]:
        raise ProviderError("CSV files can only be copied from, not to.")

    def create_playlist(self, name: str, description: str, public: bool) -> str:
        raise ProviderError("CSV files can only be copied from, not to.")

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        raise ProviderError("CSV files can only be copied from, not to.")

    def remove_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        raise ProviderError("CSV files can only be copied from, not to.")


def _map_columns(fieldnames: list[str]) -> dict[str, str]:
    by_lower = {f.strip().lower(): f for f in fieldnames}
    out = {}
    for field, names in _COLUMNS.items():
        for n in names:
            if n in by_lower:
                out[field] = by_lower[n]
                break
    return out
