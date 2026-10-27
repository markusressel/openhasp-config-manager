from openhasp_config_manager.gui.domain.variables.usages import DeviceFiles, Usage, VariableUsages
from tests import TestBase


def _write(root, files):
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content)


def _index(root, *devices):
    return VariableUsages(root, [DeviceFiles(root / device, [root / f for f in files]) for device, files in devices])


def _places(root, usages):
    return [(str(usage.path.relative_to(root.resolve())), usage.line, usage.column, usage.length) for usage in usages]


class TestUsages(TestBase):
    def test_a_variable_is_used_where_a_template_names_it(self, tmp_path):
        # GIVEN
        _write(
            tmp_path,
            {
                "global.vars.yaml": "title: a\nheader:\n  height: 27\n",
                "devices/plate/page.jsonl": '{"t": "{{ title }}"}\n{"h": "{{ header.height }}", "u": "{{ title }}"}',
            },
        )
        index = _index(tmp_path, ("devices/plate", ["devices/plate/page.jsonl"]))
        file = tmp_path / "global.vars.yaml"

        # THEN
        assert _places(tmp_path, index.usages(file, "title")) == [
            ("devices/plate/page.jsonl", 1, 10, 5),
            ("devices/plate/page.jsonl", 2, 38, 5),
        ]
        assert _places(tmp_path, index.usages(file, "header.height")) == [("devices/plate/page.jsonl", 2, 10, 13)]
        # everything below a variable counts for it
        assert index.usages(file, "header") == index.usages(file, "header.height")
        assert index.usages(file, "nothing") == []

    def test_a_template_for_a_whole_object_uses_everything_below_it(self, tmp_path):
        _write(
            tmp_path,
            {
                "global.vars.yaml": "a:\n  b:\n    c: 1\n",
                "devices/plate/page.jsonl": '{"x": "{{ a.b }}", "y": "{{ a.items() }}"}',
            },
        )
        index = _index(tmp_path, ("devices/plate", ["devices/plate/page.jsonl"]))
        assert len(index.usages(tmp_path / "global.vars.yaml", "a.b.c")) == 2

    def test_objects_use_the_theme_of_their_type(self, tmp_path):
        _write(
            tmp_path,
            {"theme.yaml": "theme:\n  obj:\n    btn:\n      radius: 4\n", "devices/plate/page.jsonl": '{"obj": "btn"}'},
        )
        index = _index(tmp_path, ("devices/plate", ["devices/plate/page.jsonl"]))
        assert _places(tmp_path, index.usages(tmp_path / "theme.yaml", "theme.obj.btn.radius")) == [
            ("devices/plate/page.jsonl", 1, 9, 3)
        ]

    def test_objects_that_set_a_property_themselves_do_not_use_the_theme_value(self, tmp_path):
        _write(
            tmp_path,
            {
                "theme.yaml": "theme:\n  obj:\n    btn:\n      radius: 4\n      bg_color: 1\n",
                "devices/plate/page.jsonl": '{"obj": "btn", "radius": 2}\n{"obj": "btn"}',
            },
        )
        index = _index(tmp_path, ("devices/plate", ["devices/plate/page.jsonl"]))
        file = tmp_path / "theme.yaml"

        # THEN: only the second button gets the radius of the theme, but both get the color
        assert _places(tmp_path, index.usages(file, "theme.obj.btn.radius")) == [("devices/plate/page.jsonl", 2, 9, 3)]
        assert len(index.usages(file, "theme.obj.btn.bg_color")) == 2
        assert len(index.usages(file, "theme.obj.btn")) == 2

    def test_a_theme_property_every_object_replaces_is_unused(self, tmp_path):
        _write(
            tmp_path,
            {
                "theme.yaml": "theme:\n  obj:\n    btn:\n      radius: 4\n",
                "devices/plate/page.jsonl": '{"obj": "btn", "radius": 2}',
            },
        )
        index = _index(tmp_path, ("devices/plate", ["devices/plate/page.jsonl"]))
        assert [leaf.name for leaf in index.unused()[(tmp_path / "theme.yaml").resolve()]] == ["theme.obj.btn.radius"]

    def test_the_value_of_a_used_variable_uses_other_variables(self, tmp_path):
        _write(
            tmp_path,
            {
                "global.vars.yaml": "subtitle: '{{ chained }}'\nchained: x\nlonely: '{{ other }}'\nother: y\n",
                "devices/plate/page.jsonl": '{"x": "{{ subtitle }}"}',
            },
        )
        index = _index(tmp_path, ("devices/plate", ["devices/plate/page.jsonl"]))
        file = tmp_path / "global.vars.yaml"
        assert _places(tmp_path, index.usages(file, "chained")) == [("global.vars.yaml", 1, 14, 7)]
        assert index.usages(file, "other") == []

    def test_a_multi_line_value_belongs_to_its_variable(self, tmp_path):
        _write(
            tmp_path,
            {
                "global.vars.yaml": "long: |\n  a {{ one }}\n  b {{ two }}\none: 1\ntwo: 2\n",
                "devices/plate/page.jsonl": '{"x": "{{ long }}"}',
            },
        )
        index = _index(tmp_path, ("devices/plate", ["devices/plate/page.jsonl"]))
        file = tmp_path / "global.vars.yaml"
        assert _places(tmp_path, index.usages(file, "one")) == [("global.vars.yaml", 2, 7, 3)]
        assert _places(tmp_path, index.usages(file, "two")) == [("global.vars.yaml", 3, 7, 3)]

    def test_usages_of_all_devices_are_listed(self, tmp_path):
        _write(
            tmp_path,
            {
                "global.vars.yaml": "title: a\n",
                "devices/a/page.jsonl": '{"x": "{{ title }}"}',
                "devices/b/page.jsonl": '{"x": "{{ title }}"}',
            },
        )
        index = _index(tmp_path, ("devices/a", ["devices/a/page.jsonl"]), ("devices/b", ["devices/b/page.jsonl"]))
        assert [usage.path.parent.name for usage in index.usages(tmp_path / "global.vars.yaml", "title")] == ["a", "b"]

    def test_the_path_can_be_unresolved(self, tmp_path):
        _write(tmp_path, {"global.vars.yaml": "t: 1\n", "devices/a/page.jsonl": '{"x": "{{ t }}"}'})
        index = _index(tmp_path, ("devices/a", ["devices/a/page.jsonl"]))
        assert index.usages(tmp_path / "devices" / ".." / "global.vars.yaml", "t") == [
            Usage((tmp_path / "devices/a/page.jsonl").resolve(), 1, 10, 1)
        ]


class TestUsedNames(TestBase):
    def test_variable_files_whose_variables_a_device_uses(self, tmp_path):
        # GIVEN
        _write(
            tmp_path,
            {
                "theme.yaml": "theme:\n  obj:\n    btn:\n      radius: 4\n",
                "other_theme.yaml": "theme:\n  obj:\n    slider:\n      radius: 4\n  header:\n    color: red\n",
                "global.vars.yaml": "screen:\n  width: 480\nid:\n  time: 10\n",
                "devices/plate/page.jsonl": '{"obj": "btn", "text": "{{ id.time }}"}',
            },
        )

        # WHEN
        result = _index(tmp_path, ("devices/plate", ["devices/plate/page.jsonl"])).used_names(tmp_path / "devices/plate")

        # THEN: no template refers to `theme`, but the button gets its defaults. The theme of sliders is not used here
        assert {str(path.relative_to(tmp_path.resolve())): names for path, names in result.items()} == {
            "theme.yaml": ["theme"],
            "global.vars.yaml": ["id"],
        }

    def test_scope_chained_values_and_broken_files(self, tmp_path):
        # GIVEN
        _write(
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
        used = ["common/header.jsonl", "devices/plate/home/page.jsonl"]

        # WHEN
        result = _index(tmp_path, ("devices/plate", used)).used_names(tmp_path / "devices/plate")

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

    def test_a_device_without_files_uses_nothing(self, tmp_path):
        _write(tmp_path, {"global.vars.yaml": "a: 1\n"})
        assert _index(tmp_path, ("devices/a", [])).used_names(tmp_path / "devices/other") == {}
