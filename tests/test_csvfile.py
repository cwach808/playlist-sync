from urllib.parse import unquote

import pytest

from playlist_sync.amazon import bookmarklet_url, write_install_page
from playlist_sync.providers import ProviderError, parse_url
from playlist_sync.providers.csvfile import CsvFileProvider, parse_duration


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_reads_our_amazon_export(tmp_path):
    path = write(tmp_path, "My Likes.csv",
                 'Title,Artist,Album,Duration\n'
                 '"Mr. Brightside","The Killers","Hot Fuss","03:42"\n'
                 '"September","Earth, Wind & Fire","The Best Of","03:35"\n'
                 '"Under Pressure","Queen; David Bowie","Hot Space","04:08"\n')
    pl = CsvFileProvider().read_playlist(path)

    assert pl.name == "My Likes"
    assert [t.title for t in pl.tracks] == ["Mr. Brightside", "September", "Under Pressure"]
    assert pl.tracks[0].duration_ms == 222_000
    assert pl.tracks[1].artists == ("Earth, Wind & Fire",)  # comma inside a name survives
    assert pl.tracks[2].artists == ("Queen", "David Bowie")


def test_reads_exportify_style_columns(tmp_path):
    path = write(tmp_path, "road_trip.csv",
                 "Track Name,Artist Name(s),Album Name,Duration (ms),ISRC\n"
                 "Dreams,Fleetwood Mac,Rumours,257800,USWB10400234\n")
    track = CsvFileProvider().read_playlist(path).tracks[0]
    assert (track.title, track.artists, track.duration_ms, track.isrc) == (
        "Dreams", ("Fleetwood Mac",), 257_800, "USWB10400234")


def test_repeat_download_suffix_is_dropped(tmp_path):
    path = write(tmp_path, "My Likes (1).csv", "Title,Artist\nA,B\n")
    assert CsvFileProvider().read_playlist(path).name == "My Likes"


def test_missing_columns_explained(tmp_path):
    path = write(tmp_path, "bad.csv", "Song\nHello\n")
    with pytest.raises(ProviderError, match="artist column"):
        CsvFileProvider().read_playlist(path)


def test_missing_file_explained(tmp_path):
    with pytest.raises(ProviderError, match="not found"):
        CsvFileProvider().read_playlist(str(tmp_path / "gone.csv"))


def test_csv_paths_are_recognized(tmp_path):
    service, playlist_id = parse_url(str(tmp_path / "x.CSV"))
    assert service == "csv" and playlist_id.endswith("x.CSV")


@pytest.mark.parametrize("raw, ms", [
    ("03:47", 227_000), ("1:02:03", 3_723_000), ("227000", 227_000), ("227", 227_000),
    ("", None), ("n/a", None),
])
def test_parse_duration(raw, ms):
    assert parse_duration(raw) == ms


def test_install_page_embeds_the_bookmarklet(tmp_path):
    url = bookmarklet_url()
    assert url.startswith("javascript:")
    assert "__plsyncExporter" in unquote(url)
    page = write_install_page(tmp_path).read_text()
    assert 'href="javascript:' in page and "drag this button" in page


def test_exportify_multiple_artists_split_on_commas(tmp_path):
    path = write(tmp_path, "x.csv",
                 'Track Name,Artist Name(s)\nUnder Pressure,"Queen,David Bowie"\n')
    assert CsvFileProvider().read_playlist(path).tracks[0].artists == ("Queen", "David Bowie")
