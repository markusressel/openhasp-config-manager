from openhasp_config_manager.util import merge_dict_recursive
from tests import TestBase


class TestUtil(TestBase):
    def test_merge_dict_recursive(self, tmp_path):
        # GIVEN

        d1 = {"A": {"B": {"C": "D", "D": "E"}}}

        d2 = {"A": {"B": {"D": "E"}}}

        # WHEN
        result = merge_dict_recursive(d1, d2)

        # THEN
        assert result == {"A": {"B": {"C": "D", "D": "E"}}}
        assert (d1 | d2) != {"A": {"B": {"C": "D", "D": "E"}}}
