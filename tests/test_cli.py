from typer.testing import CliRunner

from playlist_sync.cli import _expand_wildcards, app


def test_wildcard_inside_quotes_is_expanded(tmp_path):
    folder = tmp_path / "Amazon Music Exports"
    folder.mkdir()
    (folder / "b.csv").write_text("Title,Artist\n")
    (folder / "a.csv").write_text("Title,Artist\n")
    assert _expand_wildcards([f"{folder}/*.csv"]) == [str(folder / "a.csv"), str(folder / "b.csv")]


def test_urls_are_left_alone():
    url = "https://music.youtube.com/playlist?list=PLx"
    assert _expand_wildcards([url]) == [url]


def test_wildcard_with_no_matches_explains(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYLIST_SYNC_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["copy", f"{tmp_path}/nothing/*.csv", "--to", "spotify"])
    assert result.exit_code == 1
    assert "No files match" in result.output
