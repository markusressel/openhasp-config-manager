import random

from openhasp_config_manager.gui.domain.source.edit import matching_bracket
from openhasp_config_manager.gui.domain.source.objects import foldable, object_at_line, scan_objects
from openhasp_config_manager.gui.domain.source.structure import TextStructure
from openhasp_config_manager.gui.domain.source.syntax import Language
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
 "x": 5} {"id": 4} {
 "id": 5
}
]
{"id": 6, "a": [
  {"b": {"c": [1]}}
]}
"""


def _structure(text: str, language: Language = Language.JSONL) -> TextStructure:
    structure = TextStructure(language)
    structure.update(text)
    return structure


def _assert_like_the_whole_text(structure: TextStructure, text: str, language: Language = Language.JSONL):
    """The structure answers what the functions that read the whole text answer."""
    lines = text.split("\n")
    objects = scan_objects(text) if language == Language.JSONL else []
    assert structure.foldable() == foldable(objects)
    for line in range(1, len(lines) + 1):
        assert structure.object_at_line(line) == object_at_line(objects, line), f"line {line}"
    offset = 0
    for number, line in enumerate(lines):
        for column in range(len(line)):
            expected = matching_bracket(text, offset + column, language)
            found = structure.matching_bracket(number, column)
            position = None if found is None else sum(len(before) + 1 for before in lines[: found[0]]) + found[1]
            assert position == expected, f"line {number + 1}, column {column}"
        offset += len(line) + 1


class TestTextStructure(TestBase):
    def test_like_the_whole_text(self):
        _assert_like_the_whole_text(_structure(TEXT), TEXT)

    def test_cursor_in_a_nested_object(self):
        # GIVEN
        structure = _structure(TEXT)

        # WHEN
        found = structure.object_at_line(17)

        # THEN
        assert (found.index, found.start_line, found.end_line) == (5, 16, 18)
        assert found.get("id").value == "6"
        assert (found.get("a").value_line, found.get("a").value_end_line) == (16, 18)

    def test_several_objects_on_a_line(self):
        structure = _structure(TEXT)
        # the first object of the line
        assert structure.object_at_line(12).index == 2
        assert structure.object_at_line(13).index == 4
        assert structure.foldable() == [(4, 10), (12, 14), (16, 18)]

    def test_unbalanced_brackets(self):
        text = '}\n] {"a": [\n1,\n{"b": 2}\n'
        structure = _structure(text)
        _assert_like_the_whole_text(structure, text)
        # not closed: the object reaches to the last line
        assert (structure.object_at_line(4).start_line, structure.object_at_line(4).end_line) == (2, 5)
        assert structure.matching_bracket(1, 9) is None
        assert structure.matching_bracket(0, 0) is None

    def test_brackets_over_several_lines(self):
        structure = _structure(TEXT)
        assert structure.matching_bracket(3, 0) == (9, 0)
        assert structure.matching_bracket(9, 0) == (3, 0)
        # in a comment, a string, or no bracket
        assert structure.matching_bracket(4, 20) is None
        assert structure.matching_bracket(1, 0) == (1, 33)
        assert structure.matching_bracket(1, 1) is None
        assert structure.matching_bracket(99, 0) is None

    def test_lines_between_objects(self):
        structure = _structure(TEXT)
        assert structure.object_at_line(1) is None
        assert structure.object_at_line(3) is None
        assert structure.object_at_line(0) is None
        assert structure.object_at_line(99) is None

    def test_other_languages_have_no_objects(self):
        structure = _structure('{\n"a": [1]\n}', Language.JSON)
        assert structure.object_at_line(2) is None
        assert structure.foldable() == []
        assert structure.matching_bracket(0, 0) == (2, 0)
        assert _structure("a: {\n}", Language.YAML).matching_bracket(0, 3) is None

    def test_edits(self):
        # GIVEN
        structure = _structure(TEXT)

        # WHEN an object is opened before the others, closed again, lines are added and removed
        for text in (
            "{\n" + TEXT,
            "{\n}\n" + TEXT,
            TEXT.replace('"id": 2,', '"id": 2,\n"x": [\n'),
            TEXT.replace('"id": 2,', '"id": 2,\n"x": [\n]'),
            TEXT.replace("]\n", ""),
            TEXT[: len(TEXT) // 2],
            "",
            TEXT,
            TEXT,
        ):
            structure.update(text)

            # THEN
            _assert_like_the_whole_text(structure, text)

    def test_random_edits(self):
        """Typing anywhere: every version of the text gives what reading it whole gives."""
        rng = random.Random(7)
        text = TEXT
        structure = _structure(text)
        for _ in range(300):
            position = rng.randrange(len(text) + 1)
            removed = rng.choice((0, 0, 1, 3))
            text = text[:position] + rng.choice(("", "{", "}", "[", "]", "\n", '"', "//", "a", ', "b": {\n')) + text[position + removed :]
            structure.update(text)
            lines = text.split("\n")
            objects = scan_objects(text)
            assert structure.foldable() == foldable(objects)
            for line in range(1, len(lines) + 1):
                assert structure.object_at_line(line) == object_at_line(objects, line)
            if "{" in text:
                position = text.index("{")
                line = text.count("\n", 0, position)
                found = structure.matching_bracket(line, position - (text.rfind("\n", 0, position) + 1))
                expected = matching_bracket(text, position)
                assert (None if found is None else sum(len(before) + 1 for before in lines[: found[0]]) + found[1]) == expected
