from pathlib import Path

import pytest

from openhasp_config_manager.gui.domain.file_tree import (
    FileKind,
    default_target_component,
    format_pages,
    relative_config_path,
    scan_file_tree,
)
from openhasp_config_manager.gui.domain.plate_session import ComponentSource
from tests import TestBase


def _component(key: str, is_common: bool = False) -> ComponentSource:
    return ComponentSource(key=key, path=Path(key), content="", is_common=is_common, sources=[])


def _names(node):
    return node.name if not node.children else (node.name, [_names(child) for child in node.children])


class TestScanFileTree(TestBase):
    def test_common_and_device_folders_with_their_relevant_files(self, tmp_path):
        # GIVEN
        for path in [
            "common/dialog/offline.jsonl",
            "common/page_header.jsonl",
            "common/image.png",
            "devices/plate/0_home/0_header.jsonl",
            "devices/plate/0_home/page.cmd",
            "devices/plate/images/logo.png",
            "devices/plate/boot.cmd",
            "devices/plate/config.json",
            "devices/plate/vars.yaml",
            "devices/plate/.hidden.jsonl",
            "devices/other/other.jsonl",
        ]:
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / path).write_text("")

        # WHEN
        roots = scan_file_tree(tmp_path / "devices" / "plate")

        # THEN
        assert [_names(root) for root in roots] == [
            ("common", [("dialog", ["offline.jsonl"]), "page_header.jsonl"]),
            ("plate", [("0_home", ["0_header.jsonl", "page.cmd"]), "boot.cmd", "vars.yaml"]),
        ]
        home = roots[1].children[0]
        assert home.kind == FileKind.FOLDER
        assert [child.kind for child in home.children] == [FileKind.JSONL, FileKind.CMD]
        assert roots[1].children[2].kind == FileKind.VARIABLES

    def test_without_common_folder(self, tmp_path):
        # GIVEN
        (tmp_path / "devices" / "plate").mkdir(parents=True)
        (tmp_path / "devices" / "plate" / "boot.cmd").write_text("")

        # WHEN
        roots = scan_file_tree(tmp_path / "devices" / "plate")

        # THEN
        assert [root.name for root in roots] == ["plate"]


class TestFormatPages(TestBase):
    def test_ranges(self):
        assert format_pages([4, 0, 2, 3, 3]) == "p0, p2–p4"
        assert format_pages([1]) == "p1"
        assert format_pages([]) == ""


class TestRelativeConfigPath(TestBase):
    def test_relative_to_the_config_directory(self, tmp_path):
        device = tmp_path / "devices" / "plate"

        assert relative_config_path(device / "0_home" / "a.jsonl", device) == "devices/plate/0_home/a.jsonl"
        assert relative_config_path(tmp_path / "common" / "b.jsonl", device) == "common/b.jsonl"


class TestDefaultTargetComponent(TestBase):
    def test_device_file_with_most_objects_on_the_page_even_if_a_shared_one_has_more(self):
        components = [_component("header", is_common=True), _component("a"), _component("b")]
        objects = {
            "header": [{"page": 1}, {"page": 1}, {"page": 1}],
            "a": [{"page": 2}],
            "b": [{"page": 1}],
        }

        assert default_target_component(components, objects, page=1) == "b"

    def test_last_device_file_if_none_has_objects_on_the_page(self):
        components = [_component("a"), _component("b"), _component("header", is_common=True)]

        assert default_target_component(components, {"header": [{"page": 3}]}, page=3) == "b"

    def test_shared_file_only_without_device_files(self):
        components = [_component("x", is_common=True), _component("y", is_common=True)]

        assert default_target_component(components, {"x": [{"page": 1}]}, page=1) == "x"
        assert default_target_component(components, {}, page=1) == "y"

    def test_no_components(self):
        assert default_target_component([], {}, page=1) is None

    def test_the_later_file_on_a_tie(self):
        components = [_component("0_header"), _component("1_content")]
        objects = {"0_header": [{"page": 1}], "1_content": [{"page": 1}]}

        assert default_target_component(components, objects, page=1) == "1_content"


@pytest.mark.usefixtures("settings")
class TestFileTreeWidget(TestBase):
    def _widget(self, tmp_path):
        from openhasp_config_manager.gui.qt.widgets.file_tree import FileTreeWidget

        for path in [
            "common/header.jsonl",
            "common/dialog/offline.jsonl",
            "devices/plate/0_home/content.jsonl",
            "devices/plate/boot.cmd",
            "devices/plate/old.cmd",
            "devices/plate/old.jsonl",
            "devices/plate/vars.yaml",
        ]:
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / path).write_text("")
        device = tmp_path / "devices" / "plate"
        widget = FileTreeWidget()
        widget.set_files(
            scan_file_tree(device),
            components={tmp_path / "common/header.jsonl": "header", device / "0_home/content.jsonl": "content"},
            used={
                device / "boot.cmd": "boot.cmd",
                tmp_path / "common/header.jsonl": "boot.cmd",
                device / "0_home/content.jsonl": "boot.cmd",
                tmp_path / "common/dialog/offline.jsonl": "offline.cmd",
            },
            used_variables={device / "vars.yaml": ["title"]},
            common_path=tmp_path / "common",
        )
        widget.update_state({"header": {0}, "content": {1, 2, 3}}, page=1, target="content")
        return widget

    def test_files_show_their_pages_and_the_target(self, tmp_path):
        # WHEN
        widget = self._widget(tmp_path)

        # THEN
        content = widget._items_by_key["content"]
        assert content.text(1) == "p1–p3"
        assert content.font(0).bold() is True
        assert widget._items_by_key["header"].font(0).bold() is False
        common, device = (widget.tree.topLevelItem(i) for i in range(2))
        assert common.text(1) == "shared"
        assert common.child(0).child(0).text(1) == "offline.cmd"

    def _visible(self, item):
        return [item.child(i).text(0) for i in range(item.childCount()) if not item.child(i).isHidden()]

    def test_files_the_plate_never_uses_are_hidden_unless_all_are_shown(self, tmp_path):
        # GIVEN
        widget = self._widget(tmp_path)
        device = widget.tree.topLevelItem(1)

        # THEN
        assert widget.show_all is False
        assert self._visible(device) == ["0_home", "boot.cmd", "vars.yaml"]

        # WHEN
        widget.set_show_all(True)

        # THEN
        assert self._visible(device) == ["0_home", "boot.cmd", "old.cmd", "old.jsonl", "vars.yaml"]
        assert device.child(3).text(1) == "not used"

    def test_show_all_is_remembered(self, tmp_path):
        # GIVEN
        self._widget(tmp_path).set_show_all(True)

        # WHEN
        widget = self._widget(tmp_path)

        # THEN
        assert widget.show_all is True
        assert len(self._visible(widget.tree.topLevelItem(1))) == 5

    def test_a_folder_without_used_files_is_hidden(self, tmp_path):
        # GIVEN
        (tmp_path / "devices/plate/unused").mkdir(parents=True)
        (tmp_path / "devices/plate/unused/a.jsonl").write_text("")

        # WHEN
        widget = self._widget(tmp_path)

        # THEN
        assert "unused" not in self._visible(widget.tree.topLevelItem(1))

    def test_selecting_a_file_highlights_it_and_a_folder_ends_the_highlight(self, tmp_path):
        # GIVEN
        widget = self._widget(tmp_path)
        highlighted = []
        widget.highlightRequested.connect(highlighted.append)

        # WHEN
        widget.tree.setCurrentItem(widget._items_by_key["content"])
        widget.tree.setCurrentItem(widget.tree.topLevelItem(0))

        # THEN
        assert highlighted == ["content", None]

    def test_double_click_opens_the_file_as_text(self, tmp_path):
        # GIVEN
        widget = self._widget(tmp_path)
        opened = []
        widget.openRequested.connect(opened.append)

        # WHEN
        widget.tree.itemDoubleClicked.emit(widget._items_by_key["header"], 0)
        widget.tree.itemDoubleClicked.emit(widget.tree.topLevelItem(0), 0)

        # THEN: the folder is not a file
        assert [path.name for path in opened] == ["header.jsonl"]

    def test_reveal_selects_the_file_without_highlighting_it(self, tmp_path):
        # GIVEN
        widget = self._widget(tmp_path)
        highlighted = []
        widget.highlightRequested.connect(highlighted.append)

        # WHEN
        widget.reveal("header")

        # THEN
        assert widget.tree.currentItem() is widget._items_by_key["header"]
        assert widget._items_by_key["header"].isSelected()
        assert highlighted == []


class TestUsedFiles(TestBase):
    def test_files_run_by_the_startup_scripts(self):
        # GIVEN
        from openhasp_config_manager.gui.domain.file_tree import used_files
        from openhasp_config_manager.openhasp_client.model.component import CmdComponent, JsonlComponent

        def cmd(name, *commands):
            return CmdComponent(name=name, type="cmd", path=Path(name), content="", commands=list(commands))

        def jsonl(name):
            return JsonlComponent(name=name, type="jsonl", path=Path(name), content="")

        cmds = [
            cmd("boot.cmd", "run L:/a.jsonl", "run L:/page.cmd"),
            cmd("page.cmd", "run L:/b.jsonl", "run L:/boot.cmd"),
            cmd("online.cmd", "run /a.jsonl", "run /c.jsonl"),
            cmd("unused.cmd", "run L:/d.jsonl"),
        ]
        jsonls = [jsonl(name) for name in ["a.jsonl", "b.jsonl", "c.jsonl", "d.jsonl"]]

        # WHEN
        result = used_files(cmds, jsonls)

        # THEN
        assert {str(path): script for path, script in result.items()} == {
            "boot.cmd": "boot.cmd",
            "a.jsonl": "boot.cmd",
            "page.cmd": "boot.cmd",
            "b.jsonl": "boot.cmd",
            "online.cmd": "online.cmd",
            "c.jsonl": "online.cmd",
        }


class TestUsedVariableFiles(TestBase):
    def test_referenced_variables(self):
        from openhasp_config_manager.processing.template_rendering import referenced_variables

        assert referenced_variables('{"text": "{{ about.title }}", "x": "{{ p1b1.x + offset }}"}') == {
            "about",
            "p1b1",
            "offset",
        }
        # a broken template: the others are found anyway
        assert referenced_variables('{"a": "{{ title }}", "b": "{{ broken", "c": "{% if night %}x{% endif %}"}') >= {"title"}

    def _write(self, tmp_path, files):
        for path, content in files.items():
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / path).write_text(content)

    def test_variable_files_whose_variables_used_files_reference(self, tmp_path):
        # GIVEN
        from openhasp_config_manager.gui.domain.file_tree import used_variable_files

        self._write(
            tmp_path,
            {
                "common/header.jsonl": '{"text": "{{ device_title }}"}',
                "devices/plate/vars.yaml": "device_title: Plate\nunused: 1\nsubtitle: '{{ chained }}'\n",
                "devices/plate/home/vars.yaml": "home_title: Home\n",
                "devices/plate/home/page.jsonl": '{"text": "{{ home_title }} {{ subtitle }}"}',
                "devices/plate/about/vars.yaml": "about_title: About\n",
                "devices/plate/about/page.jsonl": '{"text": "{{ about_title }}"}',
                "devices/plate/home/more.yaml": "chained: x\n",
                "devices/plate/chain/vars.yaml": "chained: y\n",
                "devices/plate/broken.yaml": "a: [",
            },
        )
        device = tmp_path / "devices" / "plate"
        used = [tmp_path / "common/header.jsonl", device / "home/page.jsonl"]

        # WHEN
        result = used_variable_files(scan_file_tree(device), used, device)

        # THEN
        assert {str(path.relative_to(tmp_path.resolve())): names for path, names in result.items()} == {
            # used by the common file through the device folder, and by home/page.jsonl
            "devices/plate/vars.yaml": ["device_title", "subtitle"],
            "devices/plate/home/vars.yaml": ["home_title"],
            # only through the value of subtitle
            "devices/plate/home/more.yaml": ["chained"],
            # can't be read: shown, not hidden
            "devices/plate/broken.yaml": [],
        }
