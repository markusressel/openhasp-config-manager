import pytest

# pfzy is in the optional ui group
pytest.importorskip("pfzy")

from openhasp_config_manager.gui.domain.fuzzy import filter_template_suggestions, template_variable
from tests import TestBase

SUGGESTIONS = [
    ("{{ common.pages.markus.index }}", 1),
    ("{{ common.pages.mk.index }}", 2),
    ("{{ theme.obj.btn.bg_color_pressed }}", "#33691E"),
    ("{{ device.ip }}", "192.168.2.10"),
]


class TestFuzzy(TestBase):
    def test_matches_characters_in_order_ignoring_case(self):
        [result] = filter_template_suggestions("CPMi", SUGGESTIONS[:1])
        assert "".join(result.template[p] for p in result.positions) == "cpmi"

    def test_word_starts_and_runs_rank_higher(self):
        result = filter_template_suggestions("mark", [("{{ m.a.r.k }}", 1), ("{{ pages.markus }}", 2)])
        assert [s.value for s in result] == [2, 1]

    def test_empty_query_keeps_everything_shortest_first(self):
        result = filter_template_suggestions("", SUGGESTIONS)
        assert [s.template for s in result][0] == "{{ device.ip }}"
        assert all(s.positions == () for s in result)

    @pytest.mark.parametrize(
        "template, expected",
        [("{{ device.ip }}", "device.ip"), ("{{loop}}", "loop")],
    )
    def test_template_variable(self, template, expected):
        assert template_variable(template) == expected

    def test_filter_sorts_by_score_and_maps_positions_into_the_template(self):
        # WHEN
        result = filter_template_suggestions("mki", SUGGESTIONS)

        # THEN
        assert [s.template for s in result][:2] == ["{{ common.pages.mk.index }}", "{{ common.pages.markus.index }}"]
        best = result[0]
        assert "".join(best.template[p] for p in best.positions) == "mki"
        assert best.value == 2

    def test_filter_limits_the_results(self):
        assert len(filter_template_suggestions("", SUGGESTIONS, limit=2)) == 2

    def test_filter_drops_non_matches(self):
        assert [s.template for s in filter_template_suggestions("bgpress", SUGGESTIONS)] == [
            "{{ theme.obj.btn.bg_color_pressed }}"
        ]
