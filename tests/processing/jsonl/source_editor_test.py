import pytest

from openhasp_config_manager.processing.jsonl.source_editor import JsonlSourceEditor, verify_jsonl_source
from tests import TestBase

SOURCE = """// NAVIGATION BAR

{
  // limits navigation to page numbers between first_page and last_page
  "page": "{{ common.navbar.first_page }}",
  "id": 0,
  "prev": "{{ common.navbar.last_page }}"
}
{"page": 1, "id": 2, "obj": "btn", "text": "Work"}
{
  "page": 1,
  "id": 3, // the label
  "obj": "label",
}
"""


class TestJsonlSourceEditor(TestBase):
    def test_finds_all_objects(self):
        assert JsonlSourceEditor(SOURCE).object_count == 3

    def test_without_changes_the_content_stays_the_same(self):
        assert JsonlSourceEditor(SOURCE).apply({}, set(), []) == SOURCE

    def test_changes_only_the_value(self):
        # WHEN
        result = JsonlSourceEditor(SOURCE).apply({1: {"text": "Sleep"}}, set(), [])

        # THEN
        assert result == SOURCE.replace('"text": "Work"', '"text": "Sleep"')

    def test_keeps_comments_and_templates_of_other_properties(self):
        # WHEN
        result = JsonlSourceEditor(SOURCE).apply({0: {"id": 5}}, set(), [])

        # THEN
        assert '"id": 5,' in result
        assert "// limits navigation" in result
        assert '"prev": "{{ common.navbar.last_page }}"' in result

    def test_adds_a_property_to_a_multiline_object_with_its_indentation(self):
        # WHEN
        result = JsonlSourceEditor(SOURCE).apply({2: {"text": "Desk", "x": 10}}, set(), [])

        # THEN
        assert '"obj": "label",\n  "text": "Desk",\n  "x": 10,\n}' in result
        verify_jsonl_source(
            result,
            [
                {"page": "{{ common.navbar.first_page }}", "id": 0, "prev": "{{ common.navbar.last_page }}"},
                {"page": 1, "id": 2, "obj": "btn", "text": "Work"},
                {"page": 1, "id": 3, "obj": "label", "text": "Desk", "x": 10},
            ],
        )

    def test_adds_a_property_to_a_single_line_object(self):
        # WHEN
        result = JsonlSourceEditor(SOURCE).apply({1: {"x": 4}}, set(), [])

        # THEN
        assert '{"page": 1, "id": 2, "obj": "btn", "text": "Work", "x": 4}' in result

    def test_adds_a_property_to_an_empty_object(self):
        # WHEN
        result = JsonlSourceEditor("{}\n").apply({0: {"page": 1, "id": 2}}, set(), [])

        # THEN
        assert result == '{ "page": 1, "id": 2}\n'

    def test_deletes_the_lines_of_an_object(self):
        # WHEN
        result = JsonlSourceEditor(SOURCE).apply({}, {1}, [])

        # THEN
        assert '"Work"' not in result
        verify_jsonl_source(
            result,
            [
                {"page": "{{ common.navbar.first_page }}", "id": 0, "prev": "{{ common.navbar.last_page }}"},
                {"page": 1, "id": 3, "obj": "label"},
            ],
        )

    def test_changes_of_a_deleted_object_are_dropped(self):
        # WHEN
        result = JsonlSourceEditor(SOURCE).apply({1: {"text": "Sleep"}}, {1}, [])

        # THEN
        assert "Sleep" not in result

    def test_appends_objects_as_single_lines(self):
        # WHEN
        result = JsonlSourceEditor(SOURCE.rstrip("\n")).apply({}, set(), [{"page": 2, "id": 1, "text": "ä {{ x }}"}])

        # THEN
        assert result.endswith('}\n{"page": 2, "id": 1, "text": "ä {{ x }}"}\n')

    def test_writes_strings_with_escapes(self):
        # WHEN
        result = JsonlSourceEditor(SOURCE).apply({1: {"text": 'say "hi"\n'}}, set(), [])

        # THEN
        assert '"text": "say \\"hi\\"\\n"' in result

    def test_values_with_comment_markers_in_strings_are_kept(self):
        # GIVEN
        source = '{"page": 1, "src": "L://image.png", "id": 1}\n'

        # WHEN
        result = JsonlSourceEditor(source).apply({0: {"id": 2}}, set(), [])

        # THEN
        assert result == '{"page": 1, "src": "L://image.png", "id": 2}\n'

    def test_nested_values_are_skipped(self):
        # GIVEN
        source = '{"page": 1, "options": ["a", "b"], "style": {"x": [1, 2]}, "id": 1}\n'

        # WHEN
        result = JsonlSourceEditor(source).apply({0: {"id": 2}}, set(), [])

        # THEN
        assert result == source.replace('"id": 1', '"id": 2')

    def test_unknown_index_raises(self):
        with pytest.raises(IndexError):
            JsonlSourceEditor(SOURCE).apply({7: {"x": 1}}, set(), [])

    def test_verify_raises_on_different_objects(self):
        with pytest.raises(ValueError):
            verify_jsonl_source(SOURCE, [])

    def test_removes_properties_of_a_single_line_object(self):
        source = '{"!include": "common/parts/dot.jsonl", "vars": {"a": 1}, "for": {"id": [1, 2]}}\n'

        # WHEN: in the middle and at the end, one at a time
        middle = JsonlSourceEditor(source).apply({}, set(), [], removals={0: {"vars"}})
        end = JsonlSourceEditor(source).apply({}, set(), [], removals={0: {"for"}})

        # THEN
        assert middle == '{"!include": "common/parts/dot.jsonl", "for": {"id": [1, 2]}}\n'
        assert end == '{"!include": "common/parts/dot.jsonl", "vars": {"a": 1}}\n'

    def test_removes_a_run_of_properties_and_changes_the_others(self):
        # WHEN
        result = JsonlSourceEditor(SOURCE).apply({1: {"text": "Sleep"}}, set(), [], removals={1: {"id", "obj"}})

        # THEN
        assert '{"page": 1, "text": "Sleep"}' in result

    def test_removes_the_first_properties_of_a_multiline_object_and_keeps_the_comments(self):
        # WHEN
        result = JsonlSourceEditor(SOURCE).apply({}, set(), [], removals={0: {"page"}, 2: {"page", "id"}})

        # THEN
        assert '{\n  // limits navigation to page numbers between first_page and last_page\n  "id": 0,' in result
        assert '{\n  "obj": "label",\n}' in result
        verify_jsonl_source(
            result,
            [
                {"id": 0, "prev": "{{ common.navbar.last_page }}"},
                {"page": 1, "id": 2, "obj": "btn", "text": "Work"},
                {"obj": "label"},
            ],
        )

    def test_removes_every_property(self):
        assert JsonlSourceEditor('{"page": 1, "id": 2,}\n').apply({}, set(), [], removals={0: {"page", "id"}}) == "{}\n"

    def test_removing_a_property_the_object_doesnt_have_raises(self):
        with pytest.raises(KeyError):
            JsonlSourceEditor(SOURCE).apply({}, set(), [], removals={1: {"x"}})
