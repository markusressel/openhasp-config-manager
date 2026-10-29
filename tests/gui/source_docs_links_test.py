from pathlib import Path

from openhasp_config_manager.gui.domain.source.links import (
    find_links,
    include_targets,
    link_at,
    link_targets,
    plate_names,
    resolve_link,
)
from openhasp_config_manager.gui.domain.source.syntax import Language
from tests import TestBase


class TestLinks(TestBase):
    def test_find_links(self):
        line = "run L:/devices_plate1_pages.jsonl; page 1"
        links = find_links("  run L:/a_b.jsonl", Language.CMD)
        assert [(link.start, link.end, link.target) for link in links] == [(6, 18, "a_b.jsonl")]
        assert find_links('run L:/x.cmd "L:/y.cmd"', Language.CMD)[1].target == "y.cmd"
        assert find_links(line, Language.JSONL) == []
        assert find_links("run L:/image.png", Language.CMD) == []

    def test_link_at(self):
        assert link_at("run L:/a.jsonl", 8, Language.CMD).target == "a.jsonl"
        assert link_at("run L:/a.jsonl", 2, Language.CMD) is None
        assert link_at("run L:/a.jsonl", 14, Language.CMD) is None

    def test_plate_names(self):
        root = Path("/cfg")
        assert plate_names(root / "common" / "nav" / "bar.jsonl", root) == {
            "common_nav_bar.jsonl",
            "nav_bar.jsonl",
            "bar.jsonl",
        }

    def test_resolve_prefers_the_closest_file(self):
        root = Path("/cfg")
        files = [root / "devices" / "a" / "pages.jsonl", root / "devices" / "b" / "pages.jsonl", root / "common" / "x.jsonl"]
        assert resolve_link("pages.jsonl", files, root, root / "devices" / "b" / "boot.cmd") == files[1]
        assert resolve_link("devices_a_pages.jsonl", files, root, root / "devices" / "b" / "boot.cmd") == files[0]
        assert resolve_link("nope.jsonl", files, root, root / "boot.cmd") is None

    def test_link_targets_leave_out_hidden_folders(self, tmp_path):
        for name in ("common/a.jsonl", "devices/p/boot.cmd", "devices/p/vars.yaml", ".git/b.jsonl", "devices/.c.jsonl"):
            (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / name).write_text("")
        assert sorted(path.relative_to(tmp_path).as_posix() for path in link_targets(tmp_path)) == [
            "common/a.jsonl",
            "devices/p/boot.cmd",
        ]


class TestIncludeLinks(TestBase):
    def test_the_path_of_an_include_is_a_link(self):
        line = '{"!include": "common/parts/tile.jsonl", "vars": {"x": "common/other.jsonl"}}'
        [link] = find_links(line, Language.JSONL)
        assert (link.start, link.end, link.target, link.kind) == (14, 37, "common/parts/tile.jsonl", "include")
        assert link_at(line, 20, Language.JSONL).kind == "include"
        assert link_at(line, 3, Language.JSONL) is None

    def test_the_files_an_include_can_name(self, tmp_path):
        (tmp_path / "common" / "parts").mkdir(parents=True)
        for name in ["common/parts/tile.jsonl", "common/boot.cmd", "a.jsonl", ".hidden.jsonl"]:
            (tmp_path / name).write_text("")
        assert include_targets(tmp_path) == ["a.jsonl", "common/parts/tile.jsonl"]
