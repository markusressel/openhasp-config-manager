from openhasp_config_manager.util import contains_nested_dict_key, merge_dict_recursive
from tests import TestBase


class TestUtil(TestBase):
    def test_contains_nested_key_true(self, tmp_path):
        # GIVEN
        d = {"a": {"items": {"b": 1}}}

        # WHEN
        result = contains_nested_dict_key(d, "items")
        assert result is True

    def test_contains_nested_key_false(self, tmp_path):
        # GIVEN
        d = {"a": {"items": {"b": 1}}}

        # WHEN
        result = contains_nested_dict_key(d, "test")
        assert result is False

    def test_merge_dict_recursive(self, tmp_path):
        # GIVEN

        d1 = {"A": {"B": {"C": "D", "D": "E"}}}

        d2 = {"A": {"B": {"D": "E"}}}

        # WHEN
        result = merge_dict_recursive(d1, d2)

        # THEN
        assert result == {"A": {"B": {"C": "D", "D": "E"}}}
        assert (d1 | d2) != {"A": {"B": {"C": "D", "D": "E"}}}
