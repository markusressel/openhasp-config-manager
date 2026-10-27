import pytest

from openhasp_config_manager.gui.domain.source.rename import id_at_line, rename_object_id
from tests import TestBase

TEXT = """{"page": 1, "id": 1, "obj": "cont"}
{"id": 2, "parentid": 1}
{"id": 3, "parentid": 1, "text": "p1b1"}
{"page": 2, "id": 1}
{"id": 5, "parentid": 1}
{"id": "{{ x }}"}
"""


class TestRenameId(TestBase):
    def test_changes_the_id_and_the_children_on_the_same_page(self):
        result = rename_object_id(TEXT, 1, 9)
        assert result.lines == [1, 2, 3]
        assert result.text.split("\n")[:5] == [
            '{"page": 1, "id": 9, "obj": "cont"}',
            '{"id": 2, "parentid": 9}',
            '{"id": 3, "parentid": 9, "text": "p1b1"}',
            '{"page": 2, "id": 1}',
            '{"id": 5, "parentid": 1}',
        ]

    def test_other_page_keeps_its_children(self):
        result = rename_object_id(TEXT, 4, 7)
        assert result.lines == [4, 5]
        assert result.text.split("\n")[3:5] == ['{"page": 2, "id": 7}', '{"id": 5, "parentid": 7}']

    def test_same_id_changes_nothing(self):
        result = rename_object_id(TEXT, 2, 2)
        assert result.text == TEXT and result.lines == []

    def test_id_in_use(self):
        with pytest.raises(ValueError, match="already used on this page"):
            rename_object_id(TEXT, 2, 3)

    def test_no_object_and_no_plain_id(self):
        with pytest.raises(ValueError, match="no object"):
            rename_object_id("\n\n", 1, 2)
        with pytest.raises(ValueError, match="not a plain number"):
            rename_object_id(TEXT, 6, 2)
        with pytest.raises(ValueError, match="not a plain number"):
            rename_object_id('{"page": 1}', 1, 2)

    def test_id_at_line(self):
        assert id_at_line(TEXT, 2) == 2
        assert id_at_line(TEXT, 6) is None
        assert id_at_line("", 1) is None
