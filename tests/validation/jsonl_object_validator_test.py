import textwrap

from openhasp_config_manager.validation.jsonl import JsonlObjectValidator
from tests import TestBase


class TestJsonlObjectValidator(TestBase):
    def test_single_object_valid(self):
        # GIVEN
        under_test = JsonlObjectValidator()

        data = textwrap.dedent("""
        {"page": 0, "id": 5, "obj": "btn", "action": "prev", "x": 0, "y": 290, "w": 159, "h": 30, "bg_color": "#2C3E50", "text": "\ue141", "text_color": "#FFFFFF", "radius": 0, "border_side": 0, "text_font": 28}
        """).strip()

        # WHEN
        under_test.validate(data=data)

        # THEN
        assert True

    def test_multi_object_valid(self):
        # GIVEN
        under_test = JsonlObjectValidator()

        data = textwrap.dedent("""
        {"page": 1, "id": 0, "prev": 9}
        {"page": 9, "id": 0, "next": 1}
        {"page": 0, "id": 5, "obj": "btn", "action": "prev", "x": 0, "y": 290, "w": 159, "h": 30, "bg_color": "#2C3E50", "text": "\ue141", "text_color": "#FFFFFF", "radius": 0, "border_side": 0, "text_font": 28}
        {"page": 0, "id": 6, "obj": "btn", "action": "back", "x": 161, "y": 290, "w": 159, "h": 30, "bg_color": "#2C3E50", "text": "\ue2dc", "text_color": "#FFFFFF", "radius": 0, "border_side": 0, "text_font": 22}
        {"page": 0, "id": 7, "obj": "btn", "action": "next", "x": 322, "y": 290, "w": 159, "h": 30, "bg_color": "#2C3E50", "text": "\ue142", "text_color": "#FFFFFF", "radius": 0, "border_side": 0, "text_font": 28}
        """).strip()

        # WHEN
        under_test.validate(data=data)

        # THEN
        assert True

    def test_single_object_invalid_wrong_id_range(self):
        # GIVEN
        under_test = JsonlObjectValidator()

        data = textwrap.dedent("""
        {"page": 0, "id": 300, "obj": "btn"}
        """).strip()

        try:
            # WHEN
            under_test.validate(data=data)
            assert False
        except Exception as ex:
            # THEN
            assert str(ex) == "Object has invalid id '300', must be in range: [0..254]"

    def test_single_object_invalid_duplicate_id(self):
        # GIVEN
        under_test = JsonlObjectValidator()

        data = textwrap.dedent("""
        {"page": 0, "id": 5, "obj": "btn", "action": "prev", "x": 0, "y": 290, "w": 159, "h": 30, "bg_color": "#2C3E50", "text": "\ue141", "text_color": "#FFFFFF", "radius": 0, "border_side": 0, "text_font": 28}
        {"page": 0, "id": 5, "obj": "btn", "action": "prev", "x": 0, "y": 290, "w": 159, "h": 30, "bg_color": "#2C3E50", "text": "\ue141", "text_color": "#FFFFFF", "radius": 0, "border_side": 0, "text_font": 28}
        """).strip()

        try:
            # WHEN
            under_test.validate(data=data)
            assert False
        except Exception as ex:
            # THEN
            assert "Duplicate id detected: p0b5" in str(ex)

    def test_single_object_invalid_wrong_align_keyword(self):
        # GIVEN
        under_test = JsonlObjectValidator()

        data = textwrap.dedent("""
        {"page": 0, "id": 5, "obj": "btn", "align": "wrong" }
        """).strip()

        try:
            # WHEN
            under_test.validate(data=data)
            assert False
        except Exception as ex:
            # THEN
            assert str(ex) == "Invalid 'align' string value: 'wrong', must be one of: ['left', 'center', 'right', 0, 1, 2]"

    def test_single_object_invalid_wrong_align_number(self):
        # GIVEN
        under_test = JsonlObjectValidator()

        data = textwrap.dedent("""
        {"page": 0, "id": 5, "obj": "btn", "align": 4 }
        """).strip()

        try:
            # WHEN
            under_test.validate(data=data)
            assert False
        except Exception as ex:
            # THEN
            assert str(ex) == "Invalid 'align' integer value: '4', must be one of: ['left', 'center', 'right', 0, 1, 2]"
