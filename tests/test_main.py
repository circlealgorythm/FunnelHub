from pathlib import Path

from funnelhub.main import safe_inbox_dist_file


def test_safe_inbox_dist_file_allows_files_inside_dist(tmp_path: Path) -> None:
    dist_path = tmp_path / "dist"
    asset_path = dist_path / "assets" / "app.js"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_text("console.log('ok')", encoding="utf-8")

    assert safe_inbox_dist_file(dist_path, "assets/app.js") == asset_path.resolve()


def test_safe_inbox_dist_file_blocks_path_traversal(tmp_path: Path) -> None:
    dist_path = tmp_path / "inbox-app" / "dist"
    dist_path.mkdir(parents=True)
    secret_path = tmp_path / "pyproject.toml"
    secret_path.write_text("[project]\nname = 'secret'\n", encoding="utf-8")

    assert safe_inbox_dist_file(dist_path, "../../pyproject.toml") is None
