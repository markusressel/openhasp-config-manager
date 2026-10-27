from pathlib import Path

from openhasp_config_manager.gui.domain.navigation_history import Location, NavigationHistory
from tests import TestBase

A = Location(Path("a"), 1, 1)
B = Location(Path("b"), 5, 3)
C = Location(Path("c"), 2, 1)


class TestNavigationHistory(TestBase):
    def test_back_returns_to_where_the_jumps_came_from_and_forward_undoes_it(self):
        # GIVEN: A -> B -> C
        history = NavigationHistory()
        history.jumped(A)
        history.jumped(B)

        # THEN
        assert history.back(C) == B
        assert history.back(B) == A
        assert history.back(A) is None
        assert history.forward(A) == B
        assert history.forward(B) == C
        assert history.forward(C) is None

    def test_a_new_jump_drops_what_was_forward(self):
        history = NavigationHistory()
        history.jumped(A)
        assert history.back(B) == A
        history.jumped(A)
        assert history.forward(A) is None

    def test_the_same_origin_is_recorded_once(self):
        history = NavigationHistory()
        history.jumped(A)
        history.jumped(A)
        assert history.back(B) == A
        assert history.back(A) is None

    def test_places_that_are_gone_or_current_are_skipped(self):
        history = NavigationHistory()
        history.jumped(A)
        history.jumped(B)
        assert history.back(B, exists=lambda location: location != A) is None
        history.jumped(A)
        assert history.back(A) is None

    def test_the_history_is_limited(self):
        history = NavigationHistory(limit=2)
        for index in range(5):
            history.jumped(Location(Path("a"), index, 1))
        assert history.back(C).line == 4
        assert history.back(C).line == 3
        assert history.back(C) is None
