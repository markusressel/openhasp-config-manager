from pathlib import Path

from openhasp_config_manager.gui.domain.source_docs import describe_property
from openhasp_config_manager.gui.domain.source_links import find_links, link_at, plate_names, resolve_link
from openhasp_config_manager.gui.domain.source_syntax import Language
from tests import TestBase


class TestDocs(TestBase):
    def test_known_and_unknown(self):
        assert "pixels" in describe_property("x")
        assert describe_property("nope") is None

    def test_suffix_is_part_and_state(self):
        text = describe_property("bg_color12")
        assert text.startswith(describe_property("bg_color"))
        assert "part 1 is the indicator or needle" in text and "state 2 is pressed, not toggled" in text
        assert "part 0 is the main part" in describe_property("text_color00")
        assert "state 0 is default" in describe_property("text_color00")

    def test_parts_depend_on_the_object(self):
        assert "part 2 is the knob;" in describe_property("bg_color20", "switch")
        assert "the colored track" in describe_property("bg_color10", "switch")
        assert "the spinning segment" in describe_property("line_width10", "spinner")
        assert "the tab buttons" in describe_property("text_font40", "tabview")
        assert "the indicator or needle" in describe_property("bg_color10", "btn")
        assert "the items/buttons" in describe_property("bg_color40", "unknown")

    def test_state_beyond_the_known_ones(self):
        text = describe_property("bg_color09")
        assert "part 0" in text and "state 9" not in text

    def test_not_a_property(self):
        assert describe_property("nope02") is None
        assert describe_property("12") is None


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
