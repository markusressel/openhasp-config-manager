from openhasp_config_manager.gui.domain.problems import Severity
from openhasp_config_manager.gui.domain.variables.unused import find_unused_variables
from openhasp_config_manager.gui.domain.variables.usages import DeviceFiles, VariableUsages
from tests import TestBase


def _write(root, files):
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content)


def _unused(tmp_path, devices):
    """:return: file (relative) -> the names of its unused variables"""
    result = find_unused_variables(
        VariableUsages(tmp_path, [DeviceFiles(tmp_path / device, [tmp_path / f for f in files]) for device, files in devices])
    )
    return {
        str(path.relative_to(tmp_path.resolve())): [issue.message.rsplit(" ", 1)[1] for issue in found.issues]
        for path, found in result.items()
    }


class TestUnusedVariables(TestBase):
    def test_variables_no_template_uses_are_unused(self, tmp_path):
        _write(
            tmp_path,
            {
                "global.vars.yaml": "title: a\nheader:\n  height: 27\n  width: 10\nunused: 1\n",
                "devices/plate/boot.cmd": "",
                "devices/plate/page.jsonl": '{"h": "{{ header.height }}", "t": "{{ title }}"}',
            },
        )

        unused = _unused(tmp_path, [("devices/plate", ["devices/plate/page.jsonl"])])

        assert unused == {"global.vars.yaml": ["header.width", "unused"]}

    def test_a_variable_is_used_by_a_part_of_its_name_and_by_its_parts(self, tmp_path):
        _write(
            tmp_path,
            {
                "global.vars.yaml": "a:\n  b:\n    c: 1\n    d: 2\n  e: 3\nlist: [x, y]\nother:\n  f: 1\n",
                "devices/plate/page.jsonl": '{"x": "{{ a.b }}", "l": "{{ list[0] }}", "o": "{{ other.items() }}"}',
            },
        )
        # `a.b` uses everything below it, `list[0]` is a part of the list, a method can use all of the object
        assert _unused(tmp_path, [("devices/plate", ["devices/plate/page.jsonl"])]) == {"global.vars.yaml": ["a.e"]}

    def test_dynamic_subscripts_use_the_whole_object(self, tmp_path):
        _write(
            tmp_path,
            {
                "global.vars.yaml": "pages:\n  one: 1\n  two: 2\n",
                "devices/plate/page.jsonl": '{"x": "{{ pages[page] }}"}',
            },
        )
        assert _unused(tmp_path, [("devices/plate", ["devices/plate/page.jsonl"])]) == {}

    def test_the_value_of_a_used_variable_uses_other_variables(self, tmp_path):
        _write(
            tmp_path,
            {
                "global.vars.yaml": "subtitle: '{{ chained }}'\nchained: x\nlonely: '{{ other }}'\nother: y\ntitle: a\n",
                "devices/plate/page.jsonl": '{"x": "{{ subtitle }}"}',
            },
        )
        assert _unused(tmp_path, [("devices/plate", ["devices/plate/page.jsonl"])]) == {
            "global.vars.yaml": ["lonely", "other", "title"]
        }

    def test_the_theme_of_the_types_of_objects_is_used_without_a_template(self, tmp_path):
        _write(
            tmp_path,
            {
                "theme.yaml": "theme:\n  obj:\n    btn:\n      radius: 4\n    slider:\n      radius: 5\n  card:\n    bg: x\n",
                "devices/plate/page.jsonl": '{"obj": "btn"}',
            },
        )
        assert _unused(tmp_path, [("devices/plate", ["devices/plate/page.jsonl"])]) == {
            "theme.yaml": ["theme.obj.slider.radius", "theme.card.bg"]
        }

    def test_what_the_manager_reads_itself_is_used(self, tmp_path):
        _write(
            tmp_path,
            {
                "devices/plate/device.vars.yaml": "include_files:\n  - a_*.png\nbinary_images:\n  - b.png\nnothing: 1\n",
                "devices/plate/page.jsonl": "{}",
            },
        )
        assert _unused(tmp_path, [("devices/plate", ["devices/plate/page.jsonl"])]) == {
            "devices/plate/device.vars.yaml": ["nothing"]
        }

    def test_a_variable_that_any_device_uses_is_used(self, tmp_path):
        _write(
            tmp_path,
            {
                "devices/a/vars.yaml": "only_a: 1\nboth: 1\n",
                "devices/b/vars.yaml": "only_b: 1\nboth: 1\n",
                "devices/a/page.jsonl": '{"x": "{{ only_a }} {{ both }}"}',
                "devices/b/page.jsonl": '{"x": "{{ both }}"}',
            },
        )
        devices = [("devices/a", ["devices/a/page.jsonl"]), ("devices/b", ["devices/b/page.jsonl"])]
        assert _unused(tmp_path, devices) == {"devices/b/vars.yaml": ["only_b"]}

    def test_variables_are_used_through_the_scope_of_files_only(self, tmp_path):
        _write(
            tmp_path,
            {
                "devices/a/vars.yaml": "title: a\n",
                "devices/b/vars.yaml": "title: b\n",
                "devices/a/page.jsonl": '{"x": "{{ title }}"}',
            },
        )
        # `title` of b is not visible to the file of a
        assert _unused(tmp_path, [("devices/a", ["devices/a/page.jsonl"]), ("devices/b", [])]) == {
            "devices/b/vars.yaml": ["title"]
        }

    def test_common_files_see_the_variables_of_the_device_that_runs_them(self, tmp_path):
        _write(
            tmp_path,
            {
                "common/common.vars.yaml": "pages:\n  media: 1\n",
                "devices/plate/device.vars.yaml": "pages:\n  media: 5\nunused: 1\n",
                "common/header.jsonl": '{"x": "{{ pages.media }}"}',
            },
        )
        assert _unused(tmp_path, [("devices/plate", ["common/header.jsonl"])]) == {
            "devices/plate/device.vars.yaml": ["unused"]
        }

    def test_the_issues_point_at_the_key_and_its_line(self, tmp_path):
        _write(tmp_path, {"global.vars.yaml": "a:\n  b: 1\n  long_name: some value\n", "devices/plate/page.jsonl": "{}"})

        result = find_unused_variables(
            VariableUsages(tmp_path, [DeviceFiles(tmp_path / "devices/plate", [tmp_path / "devices/plate/page.jsonl"])])
        )

        [found] = result.values()
        assert found.content == "a:\n  b: 1\n  long_name: some value\n"
        assert [(issue.line, issue.column, issue.length, issue.severity) for issue in found.issues] == [
            (2, 2, 4, Severity.HINT),
            (3, 2, 21, Severity.HINT),
        ]

    def test_hidden_folders_and_broken_files_are_skipped(self, tmp_path):
        _write(
            tmp_path,
            {
                ".openhasp-config-manager/x.yaml": "a: 1\n",
                "broken.yaml": "a: [\n",
                "devices/plate/page.jsonl": "{}",
            },
        )
        assert _unused(tmp_path, [("devices/plate", ["devices/plate/page.jsonl"])]) == {}
