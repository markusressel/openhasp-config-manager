import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from openhasp_config_manager.cli import cli

DEVICE = "devices/test_device"
JSONL = """{"page": 9, "id": 1, "obj": "label", "text": "A", "x": 10}
{"page": 3, "id": 1, "obj": "btn", "text": "B"}
"""


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    pytest.importorskip("PyQt6")
    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    (root / DEVICE / "editor.jsonl").write_text(JSONL)
    (root / DEVICE / "boot.cmd").write_text("run L:/editor.jsonl\n")
    return root


def _preview(*args: str):
    return CliRunner().invoke(cli, ["preview", *args], catch_exceptions=False)


def _size(path: Path):
    from PyQt6.QtGui import QImage

    image = QImage(str(path))
    return image.width(), image.height()


class TestPreview:
    def test_all_pages_go_into_the_state_folder(self, cfg_root):
        # GIVEN: an image of a page that has no objects anymore
        folder = cfg_root / ".openhasp-config-manager" / "preview" / "test_device"
        folder.mkdir(parents=True)
        (folder / "page_5.png").write_bytes(b"old")

        # WHEN
        result = _preview("-c", str(cfg_root))

        # THEN
        assert result.exit_code == 0
        assert [Path(line) for line in result.stdout.splitlines() if line.endswith(".png")] == [
            folder / "page_3.png",
            folder / "page_9.png",
        ]
        assert sorted(path.name for path in folder.iterdir()) == ["page_3.png", "page_9.png"]
        assert _size(folder / "page_9.png") == (480, 320)
        assert (cfg_root / ".openhasp-config-manager" / ".gitignore").read_text() == "*\n"

    def test_chosen_pages_of_a_device_scaled(self, cfg_root, tmp_path):
        # WHEN
        result = _preview("-c", str(cfg_root), "-d", "test_device", "-p", "3", "--scale", "2", "-o", str(tmp_path / "out"))

        # THEN
        assert result.exit_code == 0
        assert sorted(path.name for path in (tmp_path / "out" / "test_device").iterdir()) == ["page_3.png"]
        assert _size(tmp_path / "out" / "test_device" / "page_3.png") == (960, 640)

    def test_an_unknown_device_fails(self, cfg_root):
        # WHEN
        result = _preview("-c", str(cfg_root), "-d", "nope")

        # THEN
        assert result.exit_code == 1
        assert "No device named 'nope', found: test_device" in result.stderr

    def test_a_device_that_can_not_be_rendered_fails(self, cfg_root):
        # GIVEN
        (cfg_root / DEVICE / "editor.jsonl").write_text('{"page": 9, "id": }')

        # WHEN
        result = _preview("-c", str(cfg_root))

        # THEN
        assert result.exit_code == 1
        assert "test_device: can't be rendered" in result.stderr
