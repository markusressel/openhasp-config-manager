import pytest

from openhasp_config_manager.util import add_missing_keys, merge_dict_into, merge_dict_recursive, merge_dict_shared
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

    def test_merge_does_not_share_anything_with_its_arguments(self):
        d1 = {"A": {"B": [1]}, "X": {"Y": 1}}
        d2 = {"A": {"C": [2]}, "X": {"Y": 2}}

        result = merge_dict_recursive(d1, d2)
        result["A"]["B"].append(3)
        result["A"]["C"].append(3)

        assert d1 == {"A": {"B": [1]}, "X": {"Y": 1}} and d2 == {"A": {"C": [2]}, "X": {"Y": 2}}
        assert list(merge_dict_recursive(d1, d2)) == ["A", "X"]

    def test_merge_dict_into(self):
        target = {"A": {"B": 1, "C": 2}}
        source = {"A": {"C": 3, "D": [4]}, "E": 5}

        merge_dict_into(target, source)
        target["A"]["D"].append(6)

        assert target == {"A": {"B": 1, "C": 3, "D": [4, 6]}, "E": 5}
        assert source["A"]["D"] == [4]
        with pytest.raises(AssertionError):
            merge_dict_into({"A": {}}, {"A": 1})

    def test_add_missing_keys_keeps_what_is_there(self):
        target = {"A": {"B": 1}, "C": 1}

        add_missing_keys(target, {"A": {"B": 2, "D": 3}, "C": 2, "E": {"F": 4}})

        assert target == {"A": {"B": 1, "D": 3}, "C": 1, "E": {"F": 4}}
        with pytest.raises(AssertionError):
            add_missing_keys({"A": 1}, {"A": {"B": 2}})

    def test_merge_dict_shared_reads_like_merge_dict_recursive(self):
        d1 = {"A": {"B": 1}, "X": 1}
        d2 = {"A": {"C": 2}, "X": 2}

        assert merge_dict_shared(d1, d2) == merge_dict_recursive(d1, d2) == {"A": {"B": 1, "C": 2}, "X": 2}
        assert d1 == {"A": {"B": 1}, "X": 1}
        with pytest.raises(AssertionError):
            merge_dict_shared({"A": {}}, {"A": 1})
