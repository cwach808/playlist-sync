"""Fuzzy cross-service track matching.

Services rarely share IDs (Spotify stopped exposing ISRCs to most apps in 2026, and
YouTube never did), so we compare normalized titles, artists, and durations.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher

from .models import Track

DEFAULT_THRESHOLD = 0.72
# Matches below this are accepted but flagged for the user to double-check.
CONFIDENT = 0.85

# Bracketed or dash-suffixed fragments that don't change which recording it is.
_NOISE = re.compile(
    r"\b(?:official|video|audio|lyrics?|visuali[sz]er|remaster(?:ed)?|explicit|clean|hd|hq|"
    r"4k|mv|feat|ft|featuring|with|from|single|album version|original (?:mix|version)|mono|"
    r"stereo)\b"
)
# Words that mean a *different* recording than the plain studio version.
VERSION_MARKERS = (
    "live", "remix", "acoustic", "instrumental", "karaoke", "cover", "demo",
    "sped up", "slowed", "reverb", "8d", "nightcore", "edit", "version", "mix",
    "rehearsal", "unplugged",
)
# Version-ish phrases that still mean "the normal recording".
_BENIGN_VERSIONS = re.compile(
    r"\b(?:album|original|single|explicit|clean) (?:version|mix|edit)\b|\bradio edit\b"
)
# "Artist - Song", common on YouTube uploads where the channel isn't the artist.
_ARTIST_DASH_TITLE = re.compile(r"^\s*(.{1,60}?)\s+[-\u2013\u2014]\s+(.+)$")
_FEAT_IN_TITLE = re.compile(r"[(\[]?\s*(?:feat\.?|ft\.?|featuring)\s+([^)\]]+)[)\]]?", re.I)


def _ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _clean(s: str) -> str:
    s = _ascii_fold(s).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_title(title: str) -> str:
    """Strip decorations like "(Official Video)" or "- Remastered 2011" from a title."""
    t = _ascii_fold(title).lower()

    def drop_noise(m: re.Match[str]) -> str:
        return "" if _NOISE.search(m.group(1)) else m.group(0)

    t = re.sub(r"[(\[]([^)\]]*)[)\]]", drop_noise, t)
    t = re.sub(r"\s+-\s+(.*)$", lambda m: "" if _NOISE.search(m.group(1)) else m.group(0), t)
    return _clean(t)


def featured_artists(title: str) -> list[str]:
    m = _FEAT_IN_TITLE.search(title)
    if not m:
        return []
    return [a for a in re.split(r",|&| and ", m.group(1)) if a.strip()]


def interpretations(track: Track) -> list[Track]:
    """Ways to read a track's metadata, most literal first.

    A YouTube video uploaded by "Warner Records Vault" titled "Metallica - Nothing Else
    Matters (Official Music Video)" is really artist "Metallica", song "Nothing Else
    Matters". We try both readings and keep whichever matches better.
    """
    out = [track]
    m = _ARTIST_DASH_TITLE.match(track.title)
    # Skip "Song - Remastered 2011": there the dash part is just noise, not a song title.
    if m and normalize_title(track.title) != _clean(m.group(1)):
        out.append(Track(
            title=m.group(2), artists=(m.group(1).strip(),), album=track.album,
            duration_ms=track.duration_ms, isrc=track.isrc, service_id=track.service_id,
        ))
    return out


def _artist_set(track: Track) -> set[str]:
    names = list(track.artists) + featured_artists(track.title)
    out: set[str] = set()
    for name in names:
        # YouTube often packs several artists into one string: "A & B", "A, B".
        for part in re.split(r",|&| x | and |;", name.lower()):
            if cleaned := _clean(part):
                out.add(cleaned.removeprefix("the "))
    return out


def _version_markers(title: str) -> set[str]:
    t = _BENIGN_VERSIONS.sub(" ", _clean(title))
    return {m for m in VERSION_MARKERS if re.search(rf"\b{m}\b", t)}


def score(source: Track, candidate: Track) -> float:
    """Return 0..1 confidence that `candidate` is the same recording as `source`."""
    return max(_score(reading, candidate) for reading in interpretations(source))


def _score(source: Track, candidate: Track) -> float:
    if source.isrc and candidate.isrc:
        return 1.0 if source.isrc.upper() == candidate.isrc.upper() else 0.0

    title = SequenceMatcher(
        None, normalize_title(source.title), normalize_title(candidate.title)
    ).ratio()

    src_artists, cand_artists = _artist_set(source), _artist_set(candidate)
    if src_artists and cand_artists:
        overlap = len(src_artists & cand_artists) / min(len(src_artists), len(cand_artists))
        if overlap == 0:
            # Fall back to fuzzy comparison for spelling differences ("Beyonce" vs "Beyoncé").
            overlap = max(
                SequenceMatcher(None, a, b).ratio() for a in src_artists for b in cand_artists
            )
            overlap = overlap if overlap > 0.85 else 0.0
    else:
        overlap = 0.5

    if source.duration_ms and candidate.duration_ms:
        diff_s = abs(source.duration_ms - candidate.duration_ms) / 1000
        duration = 1.0 if diff_s <= 3 else max(0.0, 1 - (diff_s - 3) / 20)
        result = 0.5 * title + 0.35 * overlap + 0.15 * duration
    else:
        result = (0.5 * title + 0.35 * overlap) / 0.85

    src_markers = _version_markers(source.title)
    # A plain title on a live/unplugged *album* is still that version.
    cand_markers = _version_markers(candidate.title) | (
        _version_markers(candidate.album or "") & src_markers
    )
    if src_markers != cand_markers:
        result -= 0.25
    return max(0.0, min(1.0, result))


def best_match(
    source: Track, candidates: Iterable[Track], threshold: float = DEFAULT_THRESHOLD
) -> tuple[Track | None, float]:
    best: Track | None = None
    best_score = 0.0
    for cand in candidates:
        s = score(source, cand)
        if s > best_score:
            best, best_score = cand, s
    if best_score < threshold:
        return None, best_score
    return best, best_score


def track_key(track: Track) -> str:
    """Stable identity for a source track, used to diff playlists between syncs."""
    if track.service_id:
        return track.service_id
    return f"{'|'.join(sorted(_artist_set(track)))}::{normalize_title(track.title)}"
