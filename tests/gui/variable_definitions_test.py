from openhasp_config_manager.gui.domain.variable_definitions import VariableDefinitions, key_at
from tests import TestBase


def _write(root, files):
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content)


class TestDefinitions(TestBase):
    def test_finds_the_line_of_the_key(self, tmp_path):
        # GIVEN
        _write(
            tmp_path,
            {
                "common/common.vars.yaml": "common:\n  header:\n    bar:\n      height: 27\n",
                "devices/plate/boot.cmd": "",
            },
        )
        definitions = VariableDefinitions(tmp_path)
        file = tmp_path / "common" / "page" / "header.jsonl"

        # WHEN
        found = definitions.find("common.header.bar.height", file)

        # THEN
        assert (found.path, found.line, found.column) == (tmp_path / "common" / "common.vars.yaml", 4, 6)
        assert definitions.find("common.header", file).line == 2
        assert definitions.find("common", file).line == 1

    def test_the_start_of_an_undefined_name_is_not_found(self, tmp_path):
        _write(tmp_path, {"global.vars.yaml": "a:\n  b: 1\n"})
        definitions = VariableDefinitions(tmp_path)
        assert definitions.find("a.c", tmp_path / "x.jsonl") is None
        assert definitions.find("nope", tmp_path / "x.jsonl") is None

    def test_deeper_folders_override_and_variables_do_not_leak_sideways(self, tmp_path):
        _write(
            tmp_path,
            {
                "global.vars.yaml": "title: root\n",
                "devices/a/vars.yaml": "title: a\n",
                "devices/b/vars.yaml": "title: b\nonly_b: 1\n",
            },
        )
        definitions = VariableDefinitions(tmp_path)
        file = tmp_path / "devices" / "a" / "page.jsonl"
        assert definitions.find("title", file).path == tmp_path / "devices" / "a" / "vars.yaml"
        assert definitions.find("title", tmp_path / "common" / "x.jsonl").path == tmp_path / "global.vars.yaml"
        assert definitions.find("only_b", file) is None

    def test_common_files_also_see_the_variables_of_the_device(self, tmp_path):
        _write(
            tmp_path,
            {
                "common/common.vars.yaml": "pages:\n  media: 1\n",
                "devices/plate/device.vars.yaml": "pages:\n  media: 5\n",
            },
        )
        definitions = VariableDefinitions(tmp_path)
        common_file = tmp_path / "common" / "header.jsonl"
        device = tmp_path / "devices" / "plate"

        # the device wins for common files, if it is given
        assert definitions.find("pages.media", common_file, device).path == device / "device.vars.yaml"
        assert definitions.find("pages.media", common_file).path == tmp_path / "common" / "common.vars.yaml"
        # but not for the files of other folders
        assert definitions.find("pages.media", tmp_path / "devices" / "other" / "p.jsonl", device) is None

    def test_a_changed_file_is_read_again_and_a_broken_one_is_skipped(self, tmp_path):
        _write(tmp_path, {"global.vars.yaml": "a: 1\n", "other.yaml": "b: [unclosed\n"})
        definitions = VariableDefinitions(tmp_path)
        file = tmp_path / "x.jsonl"
        assert definitions.find("a", file).line == 1
        assert definitions.find("b", file) is None

        (tmp_path / "global.vars.yaml").write_text("\n\na: 1\n")
        assert definitions.find("a", file).line == 3


class TestKeyAt(TestBase):
    TEXT = "common:\n  header:\n    bar:\n      height: 27\n  list:\n    - a\n"

    def test_the_key_at_a_position_is_the_dotted_name_of_the_variable(self):
        key = key_at(self.TEXT, 4, 8)
        assert (key.name, key.start, key.end) == ("common.header.bar.height", 6, 12)
        assert key_at(self.TEXT, 1, 0).name == "common"
        assert key_at(self.TEXT, 2, 3).name == "common.header"
        assert key_at(self.TEXT, 5, 2).name == "common.list"

    def test_values_and_empty_places_are_no_keys(self):
        assert key_at(self.TEXT, 4, 15) is None
        assert key_at(self.TEXT, 4, 2) is None
        assert key_at(self.TEXT, 6, 6) is None
        assert key_at(self.TEXT, 99, 0) is None

    def test_broken_yaml_has_no_keys(self):
        assert key_at("a: [\n", 1, 0) is None


class TestReadable(TestBase):
    def test_broken_files_are_not_readable(self, tmp_path):
        _write(tmp_path, {"ok.yaml": "a: 1\n", "broken.yaml": "a: [\n"})
        definitions = VariableDefinitions(tmp_path)
        assert definitions.is_readable(tmp_path / "ok.yaml")
        assert not definitions.is_readable(tmp_path / "broken.yaml")
        assert definitions.leaves(tmp_path / "broken.yaml") == []
