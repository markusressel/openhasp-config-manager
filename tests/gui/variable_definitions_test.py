from openhasp_config_manager.gui.domain.variable_definitions import VariableDefinitions, reference_at, variable_references
from tests import TestBase


def _names(line):
    return [(line[ref.start : ref.end], ref.name) for ref in variable_references(line)]


class TestReferences(TestBase):
    def test_every_part_of_a_variable_stands_for_the_variable_up_to_it(self):
        assert _names('"h": "{{ common.header.bar.height }}",') == [
            ("common", "common"),
            ("header", "common.header"),
            ("bar", "common.header.bar"),
            ("height", "common.header.bar.height"),
        ]

    def test_filters_keywords_strings_and_calls_are_no_variables(self):
        line = '"t": "{{ \'a.b\' ~ name if flag else other | upper }}{{ items.keys() }}"'
        assert _names(line) == [("name", "name"), ("flag", "flag"), ("other", "other")]

    def test_templates_in_other_text(self):
        assert _names("run L:/{{ page.name }}.jsonl") == [("page", "page"), ("name", "page.name")]
        assert _names('"x": 10, "y": "plain"') == []

    def test_statements_and_comments(self):
        assert _names("{% if theme.dark %}") == [("theme", "theme"), ("dark", "theme.dark")]
        assert _names("{# a.b #}") == []

    def test_reference_at(self):
        line = '"h": "{{ common.header }}"'
        assert reference_at(line, 10).name == "common"
        assert reference_at(line, 18).name == "common.header"
        assert reference_at(line, 15) is None
        assert reference_at(line, 2) is None


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
