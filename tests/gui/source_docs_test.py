from openhasp_config_manager.gui.domain.source.docs import (
    directive_help,
    help_at,
    object_type_at_line,
    property_help,
    theme_help_at,
)
from openhasp_config_manager.gui.domain.source.objects import scan_objects
from tests import TestBase


class TestPropertyHelp(TestBase):
    def test_known_and_unknown(self):
        assert "pixels" in property_help("x").summary
        assert property_help("nope") is None

    def test_what_kind_of_property_it_is(self):
        assert property_help("bg_color").kind == "Style property"
        assert property_help("x").kind == "Property of every object"
        assert property_help("val", "slider").kind == "slider property"
        assert property_help("bg_color10", "switch").kind == "Style property"

    def test_link_to_the_documentation(self):
        assert property_help("bg_color").url == "https://www.openhasp.com/0.7.0/design/styling/"
        assert property_help("x").url == "https://www.openhasp.com/0.7.0/design/objects/"
        assert property_help("val", "slider").url == "https://www.openhasp.com/0.7.0/design/objects/slider/"

    def test_suffix_is_part_and_state(self):
        found = property_help("bg_color12")
        assert found.summary == property_help("bg_color").summary
        assert [label for label, _ in found.details] == ["Part", "State"]
        assert dict(found.details)["Part"].startswith("1: the indicator or needle")
        assert dict(found.details)["State"] == "2: pressed, not toggled"
        assert dict(property_help("text_color00").details)["Part"].startswith("0: the main part")
        assert dict(property_help("text_color00").details)["State"] == "0: default"

    def test_parts_depend_on_the_object(self):
        def part(name, object_type):
            return dict(property_help(name, object_type).details)["Part"]

        assert part("bg_color20", "switch") == "2: the knob"
        assert part("bg_color10", "switch") == "1: the indicator (the colored track)"
        assert part("line_width10", "spinner") == "1: the spinning segment"
        assert part("text_font40", "tabview") == "4: the tab buttons"
        assert part("bg_color10", "btn").startswith("1: the indicator or needle")
        assert part("bg_color40", "unknown").startswith("4: the items/buttons")

    def test_state_beyond_the_known_ones(self):
        assert [label for label, _ in property_help("bg_color09").details] == ["Part"]

    def test_not_a_property(self):
        assert property_help("nope02") is None
        assert property_help("12") is None

    def test_meaning_depends_on_the_type(self):
        assert "toggle button" in property_help("val", "btn").summary
        assert "left" in property_help("align", "label").summary
        assert property_help("val", "led").summary.startswith("The brightness")

    def test_without_a_type_every_meaning_is_listed(self):
        text = property_help("type").summary
        assert "`arc`" in text and "`spinner`" in text and "`linemeter`" in text

    def test_types_not_known_get_the_generic_explanation(self):
        assert property_help("angle", "nope").summary == property_help("angle").summary


class TestHelpAt(TestBase):
    def test_the_key_at_the_column_with_the_parts_of_its_object(self):
        text = '{"obj": "switch",\n "bg_color20": "red", "nope": 1}'
        objects = scan_objects(text)
        line = text.split("\n")[1]

        found = help_at(objects, line, 2, line.index("bg_color20"))
        assert found.name == "bg_color20" and dict(found.details)["Part"] == "2: the knob"
        assert help_at(objects, line, 2, line.index("red")) is None
        assert help_at(objects, line, 2, line.index("nope")) is None

    def test_outside_of_objects(self):
        assert help_at([], '"x": 1', 1, 1).name == "x"

    def test_type_of_the_object(self):
        objects = scan_objects('{"obj": "slider",\n "val": 1}\n{"x": 1}')
        assert object_type_at_line(objects, 2) == "slider"
        assert object_type_at_line(objects, 3) is None
        assert object_type_at_line(objects, 9) is None


class TestThemeHelpAt(TestBase):
    THEME = (
        "theme:\n  text_color: x\n  obj:\n    btn:\n      bg_color04: '#fff'\n      radius: 4\n    label:\n      bogus: 1\n"
    )

    def test_explains_a_default_property_of_an_object_type(self):
        # line 5: `      bg_color04: '#fff'`
        found = theme_help_at(self.THEME, 5, 8)
        assert found is not None
        assert found.name == "bg_color04"
        assert found.kind == "Style property"
        assert "Background color" in found.summary
        assert found.details[0] == ("Default", "for every `btn` object that doesn't set `bg_color04` itself")
        # the part and state of the suffix, for a button
        assert [label for label, _ in found.details] == ["Default", "Part", "State"]
        assert found.details[2][1].startswith("4:")

    def test_the_meaning_for_the_type_is_used(self):
        found = theme_help_at(self.THEME, 6, 8)
        assert found is not None and found.name == "radius"

    def test_other_keys_have_no_help(self):
        # a key outside of theme.obj, an object type, a value, an unknown property
        assert theme_help_at(self.THEME, 2, 4) is None
        assert theme_help_at(self.THEME, 4, 6) is None
        assert theme_help_at(self.THEME, 5, 22) is None
        assert theme_help_at(self.THEME, 8, 8) is None

    def test_a_text_that_is_no_yaml_has_no_help(self):
        assert theme_help_at("theme: [", 1, 2) is None


class TestDirectiveHelp(TestBase):
    def test_the_keys_of_a_directive_are_explained(self):
        # GIVEN
        lines = ["{", '  "!include": "a.jsonl",', '  "vars": {"x": 1},', '  "for": {"i": [1]}', "}", '{"vars": 1}']
        objects = scan_objects("\n".join(lines))

        # THEN
        assert help_at(objects, lines[1], 2, 4).kind == "Directive"
        assert "relative to the config directory" in help_at(objects, lines[1], 2, 4).summary
        assert help_at(objects, lines[2], 3, 4).kind == "Key of an `!include`"
        assert help_at(objects, lines[3], 4, 4).name == "for"
        # not in a directive: no openHASP property either
        assert help_at(objects, lines[5], 6, 3) is None

    def test_an_unknown_directive(self):
        assert directive_help("!inc").summary == "Unknown directive: the only directive is `!include`."
        assert directive_help("page") is None
