from openhasp_config_manager.gui.domain.problems import Severity
from openhasp_config_manager.gui.domain.source.issues import find_source_issues
from openhasp_config_manager.gui.domain.source.syntax import Language
from tests import TestBase


def _issues(text, language=Language.JSONL):
    return [(i.line, i.column, i.severity, i.message) for i in find_source_issues(text, language)]


class TestJsonl(TestBase):
    def test_valid_file_has_no_issues(self):
        text = '// objects\n{"page": 1, "id": 1,}\n{\n  "page": 1, // c\n  "id": 2,\n}\n'
        assert _issues(text) == []

    def test_unclosed_object(self):
        assert _issues('{"page": 1}\n\n{"page": 2,\n') == [(3, 0, Severity.ERROR, "The object is not closed")]

    def test_invalid_json_is_reported_at_its_line(self):
        text = '{"page": 1}\n{\n  "page": 2\n  "id": 3\n}\n'
        [(line, column, severity, message)] = _issues(text)
        assert (line, severity) == (4, Severity.ERROR)
        assert message.startswith("Invalid JSON")
        assert column >= 0

    def test_invalid_json_on_the_line_of_the_object(self):
        [(line, _, _, message)] = _issues('{"page": }')
        assert line == 1 and message.startswith("Invalid JSON")

    def test_invalid_template_covers_the_template(self):
        [issue] = find_source_issues('{"text": "a {{ b + }} c"}', Language.JSONL)
        assert (issue.line, issue.column, issue.length) == (1, 12, 9)
        assert issue.message.startswith("Invalid template")

    def test_invalid_template_around_a_nested_template(self):
        [issue] = find_source_issues('{"x": "{{ p{{ page }}b1.x + }}"}', Language.JSONL)
        assert issue.message.startswith("Invalid template")

    def test_unknown_variables_are_no_issue_here(self):
        assert _issues('{"text": "{{ nope.x }}", "w": "{{ {{ a }} }}"}') == []

    def test_issues_are_in_the_order_of_the_file(self):
        text = '{"a": "{{ x + }}"}\n{"b": }\n'
        assert [line for line, *_ in _issues(text)] == [1, 2]


class TestOtherLanguages(TestBase):
    def test_json(self):
        assert _issues('{\n  "a" 1\n}\n', Language.JSON) == [(2, 6, Severity.ERROR, "Invalid JSON: Expecting ':' delimiter")]
        assert _issues('{\n  "a": {"page": 1}\n}\n', Language.JSON) == []

    def test_yaml(self):
        assert _issues("a: 1\nb: [1\n", Language.YAML)[0][2] == Severity.ERROR
        assert _issues("a: 1\nb: 2\n", Language.YAML) == []

    def test_yaml_error_without_a_position(self, monkeypatch):
        import yaml

        def fail(_text):
            raise yaml.YAMLError("odd")

        monkeypatch.setattr(yaml, "safe_load", fail)
        assert _issues("a", Language.YAML) == [(1, 0, Severity.ERROR, "Invalid YAML: odd")]

    def test_templates_in_cmd_files(self):
        assert _issues("run L:/{{ a + }}.jsonl", Language.CMD)[0][3].startswith("Invalid template")
        assert _issues("run L:/x.jsonl", Language.CMD) == []
        assert _issues("{{ broken", Language.TEXT) == []


class TestDuplicateIds(TestBase):
    def test_both_ids_are_marked(self):
        text = '{"page": 1, "id": 3}\n{\n  "page": 1,\n  "id": 3\n}\n'
        assert _issues(text) == [
            (1, 18, Severity.ERROR, "The id 3 is also used on this page by the object at line 2"),
            (4, 8, Severity.ERROR, "The id 3 is also used on this page by the object at line 1"),
        ]

    def test_the_page_is_inherited_from_the_object_before(self):
        text = '{"page": 1, "id": 3}\n{"id": 3}\n{"page": 2, "id": 3}\n'
        assert [issue[0] for issue in _issues(text)] == [1, 2]

    def test_same_id_on_other_pages_and_templates_are_fine(self):
        assert (
            _issues('{"page": 1, "id": 3}\n{"page": 2, "id": 3}\n{"page": 2, "id": "{{ a }}"}\n{"page": 2, "id": "{{ a }}"}')
            == []
        )
