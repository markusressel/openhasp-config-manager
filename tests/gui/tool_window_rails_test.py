from pathlib import Path

import pytest

from openhasp_config_manager.gui.domain.tool_window_rails import (
    Placement,
    RailClick,
    Rect,
    Side,
    arrange,
    click_action,
    place,
    side_of,
)
from tests import TestBase
from tests.gui.helpers import wait_until
from tests.helpers import DEVICE_DIR, copy_test_config

# the preview, in the middle of the window
CENTER = Rect(300, 50, 800, 500)


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    return copy_test_config(tmp_path, {f"{DEVICE_DIR}/boot.cmd": "run L:/home_page.jsonl\n"})


class TestPlacement(TestBase):
    def test_the_side_is_where_the_view_is_next_to_the_preview(self):
        assert side_of(Rect(0, 50, 290, 800), CENTER) == Side.LEFT
        assert side_of(Rect(1110, 50, 300, 800), CENTER) == Side.RIGHT
        assert side_of(Rect(300, 560, 800, 200), CENTER) == Side.BOTTOM
        assert side_of(Rect(300, 0, 800, 40), CENTER) == Side.TOP

    def test_a_column_at_the_left_that_reaches_below_the_preview_is_at_the_left(self):
        assert side_of(Rect(0, 600, 290, 200), CENTER) == Side.LEFT

    def test_a_view_below_the_preview_and_the_left_column_is_at_the_bottom(self):
        assert side_of(Rect(0, 600, 1400, 200), CENTER) == Side.BOTTOM

    def test_the_position_runs_along_the_rail(self):
        assert place(Rect(0, 70, 290, 800), CENTER) == Placement(Side.LEFT, 70)
        assert place(Rect(420, 560, 800, 200), CENTER, tab=2) == Placement(Side.BOTTOM, 420, 2)

    def test_views_are_ordered_along_the_rail_and_a_tab_group_like_its_tabs(self):
        rails = arrange(
            [
                ("logs", Placement(Side.BOTTOM, 400, 1)),
                ("devices", Placement(Side.LEFT, 0)),
                ("code", Placement(Side.BOTTOM, 400, 0)),
                ("plates", Placement(Side.BOTTOM, 900)),
                ("page", Placement(Side.BOTTOM, 400, 1)),
            ]
        )

        assert rails[Side.LEFT] == ["devices"]
        # same position and tab: in the order given
        assert rails[Side.BOTTOM] == ["code", "logs", "page", "plates"]
        assert rails[Side.RIGHT] == []

    def test_placement_survives_the_settings_and_a_broken_one_is_ignored(self):
        placement = Placement(Side.RIGHT, 120, 1)

        assert Placement.from_json(placement.to_json()) == placement
        assert Placement.from_json({"side": "middle", "position": 1}) is None
        assert Placement.from_json("left") is None

    def test_a_click_shows_a_closed_view_raises_one_behind_a_tab_and_hides_a_visible_one(self):
        assert click_action(is_open=False, is_raised=False) == RailClick.SHOW
        assert click_action(is_open=True, is_raised=False) == RailClick.RAISE
        assert click_action(is_open=True, is_raised=True) == RailClick.HIDE


class TestToolWindowRails(TestBase):
    @staticmethod
    def _shown(window):
        window.resize(1440, 900)
        window.show()
        wait_until(lambda: window.rails.side_of(window.jsonl_dock) == Side.BOTTOM)
        return window

    def test_a_button_per_view_follows_the_view(self, window):
        # GIVEN
        window = self._shown(window)
        rails = window.rails

        # THEN: every view but the preview has a button, on its side
        assert rails.button(window.preview_dock) is None
        assert rails.side_of(window.devices_dock) == Side.LEFT
        assert rails.side_of(window.properties_dock) == Side.RIGHT
        # the logs were never seen: after the others, which are in the order of their tabs
        wait_until(
            lambda: (
                [button.dock.objectName() for button in rails.buttons(Side.BOTTOM)]
                == ["jsonl_dock", "page_jsonl_dock", "plates_dock", "logs_dock"]
            )
        )
        plates = rails.button(window.plates_dock)
        assert plates.isChecked()

        # WHEN: a view behind another one of its tab group is clicked, it is raised
        plates.click()

        # THEN
        wait_until(lambda: not window.plates_dock.visibleRegion().isEmpty())
        assert plates.isChecked()

        # WHEN: clicked again, it is hidden
        plates.click()

        # THEN
        wait_until(lambda: window.plates_dock.isHidden())
        assert not plates.isChecked()

        # WHEN: clicked again, it is shown
        plates.click()

        # THEN
        wait_until(lambda: not window.plates_dock.visibleRegion().isEmpty())
        assert plates.isChecked()

        # WHEN: hidden and shown from code
        window.plates_dock.hide()
        # THEN
        assert not plates.isChecked()
        # WHEN
        window.plates_dock.show()
        # THEN
        assert plates.isChecked()

        # WHEN: closed with the action of the View menu
        window.page_jsonl_dock.toggleViewAction().trigger()

        # THEN
        assert window.page_jsonl_dock.isHidden()
        assert not rails.button(window.page_jsonl_dock).isChecked()

        # WHEN: the window state is restored
        window.restore_default_layout()

        # THEN
        assert not window.page_jsonl_dock.isHidden()
        assert rails.button(window.page_jsonl_dock).isChecked()

    def test_a_button_moves_with_its_view(self, window):
        # GIVEN
        from PyQt6.QtCore import Qt

        window = self._shown(window)

        # WHEN: the user puts the code at the right
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, window.jsonl_dock)

        # THEN
        rails = window.rails
        wait_until(lambda: rails.side_of(window.jsonl_dock) == Side.RIGHT)
        assert rails.button(window.jsonl_dock) in rails.buttons(Side.RIGHT)
        assert rails.button(window.jsonl_dock) not in rails.buttons(Side.BOTTOM)
        assert rails.rail(Side.RIGHT).isVisible()

    def test_a_dock_added_later_gets_a_button(self, window):
        # GIVEN
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QLabel

        window = self._shown(window)

        # WHEN: like the docks of the window, but not described for the rails, and hidden before it was seen
        dock = window._add_dock("Later", "later_dock", QLabel("later"))
        window.tabifyDockWidget(window.jsonl_dock, dock)
        dock.hide()

        # THEN: at the bottom, where the docks nested around the preview are
        wait_until(lambda: window.rails.side_of(dock) == Side.BOTTOM)
        assert window.rails.button(dock).text() == "Later"
        assert not window.rails.button(dock).isChecked()

        # WHEN: one in a dock area of its own
        other = window._add_dock("Right", "right_dock", QLabel("right"))
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, other)

        # THEN
        wait_until(lambda: window.rails.side_of(other) == Side.RIGHT)
        assert window.rails.button(other).isChecked()

    def test_the_rails_can_be_hidden(self, window):
        # GIVEN
        window = self._shown(window)
        rail = window.rails.rail(Side.LEFT)
        assert rail.isVisible()

        # WHEN
        window.rails.action_show_rails.setChecked(False)

        # THEN
        assert not rail.isVisible()
