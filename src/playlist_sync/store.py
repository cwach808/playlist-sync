"""SQLite state: which playlists are linked, what we've matched, and what we've added."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .models import Link, Track


def home_dir() -> Path:
    path = Path(os.environ.get("PLAYLIST_SYNC_HOME", Path.home() / ".playlist-sync"))
    path.mkdir(parents=True, exist_ok=True)
    return path


SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY,
    source_service TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_service TEXT NOT NULL,
    target_id TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_synced_at TEXT,
    UNIQUE (source_service, source_id, target_service)
);

-- Cache of cross-service lookups, shared by all links. target_id NULL = no match found.
CREATE TABLE IF NOT EXISTS matches (
    source_service TEXT NOT NULL,
    source_key TEXT NOT NULL,
    target_service TEXT NOT NULL,
    target_id TEXT,
    score REAL NOT NULL,
    PRIMARY KEY (source_service, source_key, target_service)
);

-- Source tracks we've processed for a link. target_id NULL = unmatched.
CREATE TABLE IF NOT EXISTS link_items (
    link_id INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL,
    target_id TEXT,
    display TEXT NOT NULL,
    PRIMARY KEY (link_id, source_key)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str | None = None):
        self.db = sqlite3.connect(path or home_dir() / "state.db")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    # links

    def add_link(self, link: Link) -> Link:
        cur = self.db.execute(
            "INSERT INTO links (source_service, source_id, target_service, target_id, name,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (link.source_service, link.source_id, link.target_service, link.target_id,
             link.name, _now()),
        )
        self.db.commit()
        link.id = cur.lastrowid
        return link

    def find_link(self, source_service: str, source_id: str, target_service: str) -> Link | None:
        row = self.db.execute(
            "SELECT * FROM links WHERE source_service = ? AND source_id = ? AND target_service = ?",
            (source_service, source_id, target_service),
        ).fetchone()
        return _link(row) if row else None

    def get_link(self, link_id: int) -> Link | None:
        row = self.db.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
        return _link(row) if row else None

    def links(self) -> list[Link]:
        return [_link(r) for r in self.db.execute("SELECT * FROM links ORDER BY id")]

    def delete_link(self, link_id: int) -> bool:
        cur = self.db.execute("DELETE FROM links WHERE id = ?", (link_id,))
        self.db.commit()
        return cur.rowcount > 0

    def mark_synced(self, link_id: int) -> None:
        self.db.execute("UPDATE links SET last_synced_at = ? WHERE id = ?", (_now(), link_id))
        self.db.commit()

    # match cache

    def cached_match(self, source_service: str, key: str, target_service: str):
        """Return (target_id_or_None,) if we've looked this up before, else None."""
        row = self.db.execute(
            "SELECT target_id FROM matches WHERE source_service = ? AND source_key = ?"
            " AND target_service = ?",
            (source_service, key, target_service),
        ).fetchone()
        return (row["target_id"],) if row else None

    def save_match(
        self, source_service: str, key: str, target_service: str, target_id: str | None,
        score: float,
    ) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO matches VALUES (?, ?, ?, ?, ?)",
            (source_service, key, target_service, target_id, score),
        )
        self.db.commit()

    # link items

    def link_items(self, link_id: int) -> dict[str, str | None]:
        rows = self.db.execute(
            "SELECT source_key, target_id FROM link_items WHERE link_id = ?", (link_id,)
        )
        return {r["source_key"]: r["target_id"] for r in rows}

    def set_link_item(self, link_id: int, key: str, target_id: str | None, track: Track) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO link_items VALUES (?, ?, ?, ?)",
            (link_id, key, target_id, track.display),
        )
        self.db.commit()

    def remove_link_item(self, link_id: int, key: str) -> None:
        self.db.execute(
            "DELETE FROM link_items WHERE link_id = ? AND source_key = ?", (link_id, key)
        )
        self.db.commit()

    def unmatched(self, link_id: int) -> list[str]:
        rows = self.db.execute(
            "SELECT display FROM link_items WHERE link_id = ? AND target_id IS NULL"
            " ORDER BY display",
            (link_id,),
        )
        return [r["display"] for r in rows]


def _link(row: sqlite3.Row) -> Link:
    return Link(
        id=row["id"],
        source_service=row["source_service"],
        source_id=row["source_id"],
        target_service=row["target_service"],
        target_id=row["target_id"],
        name=row["name"],
        last_synced_at=row["last_synced_at"],
    )
