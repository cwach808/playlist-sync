import pytest

from playlist_sync.matching import (
    best_match,
    interpretations,
    normalize_title,
    score,
    track_key,
)
from playlist_sync.models import Track


def t(title, *artists, ms=None, isrc=None, sid=None):
    return Track(title, tuple(artists), duration_ms=ms, isrc=isrc, service_id=sid)


@pytest.mark.parametrize("raw, expected", [
    ("Get Lucky (Official Video)", "get lucky"),
    ("Here Comes the Sun - Remastered 2009", "here comes the sun"),
    ("Mr. Brightside [HD]", "mr brightside"),
    ("Blinding Lights (feat. Someone)", "blinding lights"),
    ("Beyoncé – Halo", "beyonce halo"),
    ("Hurt (Live)", "hurt live"),  # "Live" is a different recording, keep it.
])
def test_normalize_title(raw, expected):
    assert normalize_title(raw) == expected


def test_same_song_across_services_matches():
    src = t("Get Lucky (feat. Pharrell Williams and Nile Rodgers)", "Daft Punk", ms=369_000)
    cand = t("Get Lucky", "Daft Punk", "Pharrell Williams", "Nile Rodgers", ms=370_000)
    assert score(src, cand) > 0.9


def test_youtube_style_title_matches():
    src = t("Mr. Brightside", "The Killers", ms=222_000)
    cand = t("The Killers - Mr. Brightside (Official Music Video)", "The Killers", ms=224_000)
    # Artist-in-title is common on YouTube; it lowers the score but should still pass.
    assert score(src, cand) > 0.6


def test_live_version_is_penalized():
    src = t("Hurt", "Johnny Cash", ms=218_000)
    studio = t("Hurt", "Johnny Cash", ms=218_000)
    live = t("Hurt (Live)", "Johnny Cash", ms=230_000)
    match, _ = best_match(src, [live, studio])
    assert match is studio
    assert score(src, live) < 0.72


def test_wrong_artist_rejected():
    src = t("Halo", "Beyoncé", ms=261_000)
    cand = t("Halo", "Starset", ms=261_000)
    assert best_match(src, [cand])[0] is None


def test_accented_artist_names_match():
    assert score(t("Halo", "Beyoncé"), t("Halo", "Beyonce")) > 0.9


def test_benign_version_suffix_not_penalized():
    src = t("Dreams", "Fleetwood Mac", ms=257_000)
    cand = t("Dreams (2004 Remaster)", "Fleetwood Mac", ms=257_000)
    assert score(src, cand) > 0.9


def test_isrc_is_authoritative():
    assert score(t("A", "x", isrc="USABC1"), t("B", "y", isrc="usabc1")) == 1.0
    assert score(t("A", "x", isrc="USABC1"), t("A", "x", isrc="USABC2")) == 0.0


def test_track_key_prefers_service_id():
    assert track_key(t("Song", "Artist", sid="abc")) == "abc"
    assert track_key(t("Song (Official Video)", "Artist")) == track_key(t("Song", "artist"))


# Real cases from a "Greatest 90s Hits" YouTube Music playlist.

def test_uploader_channel_is_not_the_artist():
    src = t("Metallica - Nothing Else Matters (Official Music Video)", "Warner Records Vault",
            ms=386_000)
    cand = Track("Nothing Else Matters (Remastered)", ("Metallica",), duration_ms=388_733)
    assert score(src, cand) > 0.85


def test_noise_suffix_is_not_mistaken_for_artist_dash_title():
    assert interpretations(t("Dreams - Remastered 2004", "Fleetwood Mac")) == [
        t("Dreams - Remastered 2004", "Fleetwood Mac")
    ]


def test_original_version_suffix_is_harmless():
    src = t("California Love (feat. Roger Troutman & Dr. Dre)", "2Pac", ms=285_000)
    cand = Track("California Love - Original Version", ("2Pac", "Roger", "Dr. Dre"),
                 duration_ms=284_906)
    assert score(src, cand) > 0.85


def test_rehearsal_is_a_different_recording():
    src = t("The Man Who Sold The World (MTV Unplugged)", "Nirvana", ms=218_000)
    rehearsal = Track("The Man Who Sold The World - Rehearsal", ("Nirvana",),
                      duration_ms=278_417)
    assert score(src, rehearsal) < 0.72


def test_unplugged_album_counts_as_unplugged_version():
    src = t("The Man Who Sold The World (MTV Unplugged)", "Nirvana", ms=218_000)
    cand = Track("The Man Who Sold The World", ("Nirvana",),
                 album="MTV Unplugged In New York", duration_ms=261_000)
    assert score(src, cand) > 0.72
