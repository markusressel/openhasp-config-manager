from openhasp_config_manager.gui.domain.source_objects import fold_ranges, object_at_line, scan_objects
from openhasp_config_manager.processing.jsonl.source_editor import JsonlSourceEditor
from tests import TestBase

TEXT = """// header
{"page": 1, "id": 1, "obj": "btn"}

{
  // comment with } and {
  "id": 2,
  "text": "{{ a }}",
  "opts": [1, {"x": 2}],
  "w": "33%",
}
{"id": 3,
 "x": 5}
"""


class TestScanObjects(TestBase):
    def test_lines_of_objects(self):
        objects = scan_objects(TEXT)
        assert [(o.start_line, o.end_line) for o in objects] == [(2, 2), (4, 10), (11, 12)]

    def test_same_objects_as_the_source_editor(self):
        assert len(scan_objects(TEXT)) == JsonlSourceEditor(TEXT).object_count
        for obj in scan_objects(TEXT):
            assert obj.start_line == JsonlSourceEditor(TEXT).line_of(obj.index)

    def test_properties(self):
        first, second, third = scan_objects(TEXT)
        assert [p.key for p in first.properties] == ["page", "id", "obj"]
        assert first.get("id").value == "1"
        assert first.get("obj").value == '"btn"'
        assert [p.key for p in second.properties] == ["id", "text", "opts", "w"]
        assert second.get("text").value == '"{{ a }}"'
        assert second.get("opts").value == '[1, {"x": 2}]'
        assert second.get("id").line == 6
        assert third.get("x").line == 12
        assert second.get("nope") is None

    def test_value_position(self):
        prop = scan_objects('{"id": 12}')[0].get("id")
        assert (prop.value_line, prop.value_start, prop.value_end_line, prop.value_end) == (1, 7, 1, 9)

    def test_value_over_several_lines(self):
        prop = scan_objects('{\n"a": [\n1,\n2\n],\n"b": 1}')[0].get("a")
        assert prop.value is None
        assert (prop.line, prop.value_line, prop.value_end_line) == (2, 2, 5)

    def test_key_with_template(self):
        assert scan_objects('{"a{{ b }}c": 1}')[0].properties[0].key == "a{{ b }}c"

    def test_object_not_closed(self):
        objects = scan_objects('{"a": 1}\n{\n"b": 2,\n')
        assert [(o.start_line, o.end_line) for o in objects] == [(1, 1), (2, 4)]
        assert objects[1].get("b").value == "2"

    def test_text_without_objects(self):
        assert scan_objects("") == []
        assert scan_objects("// nothing\n]\n") == []

    def test_property_without_value(self):
        assert scan_objects('{"a": , "b": 1}')[0].properties[0].key == "b"

    def test_object_at_line(self):
        objects = scan_objects(TEXT)
        assert object_at_line(objects, 1) is None
        assert object_at_line(objects, 5).index == 1
        assert object_at_line(objects, 11).index == 2
        assert object_at_line(objects, 3) is None

    def test_fold_ranges(self):
        assert fold_ranges(TEXT) == [(4, 10)]
        assert fold_ranges('{\n"a": 1\n}') == [(1, 3)]
        assert fold_ranges('{"a": 1,\n"b": 2}') == []
