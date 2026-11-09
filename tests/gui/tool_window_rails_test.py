from pathlib import Path

import pytest

from openhasp_config_manager.gui.domain.tool_window_rails import (
    RailClick,
    Side,
    Slot,
    ToolWindowLayout,
    click_action,
    drop_target,
)
from tests import TestBase
from tests.gui.helpers import wait_until
from tests.helpers import DEVICE_DIR, copy_test_config


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    return copy_test_config(tmp_path, {f"{DEVICE_DIR}/boot.cmd": "run L:/home_page.jsonl\n"})


def _layout() -> ToolWindowLayout:
    layout = ToolWindowLayout()
    layout.add("devices", Slot.LEFT_TOP, is_open=True)
    layout.add("code", Slot.BOTTOM_LEFT, is_open=True)
    layout.add("page", Slot.BOTTOM_LEFT)
    layout.add("logs", Slot.BOTTOM_RIGHT)
    return layout


class TestLayout(TestBase):
    def test_the_places_of_the_rails(self):
        assert Slot.LEFT_BOTTOM.side == Side.LEFT and Slot.LEFT_BOTTOM.secondary
        assert Slot.BOTTOM_LEFT.side == Side.BOTTOM and not Slot.BOTTOM_LEFT.secondary
        assert Slot.of(Side.RIGHT, True) == Slot.RIGHT_BOTTOM
        assert Slot.BOTTOM_LEFT.partner() == Slot.BOTTOM_RIGHT
        assert Slot.RIGHT_TOP.label == "Right top"

    def test_a_click_opens_a_closed_view_and_closes_an_open_one(self):
        assert click_action(is_open=False) == RailClick.SHOW
        assert click_action(is_open=True) == RailClick.HIDE

    def test_the_first_half_of_a_rail_is_its_first_group(self):
        # buttons of the first group at 20 and 60, of the second at 380
        assert drop_target(Side.LEFT, 400, 10, [20, 60], [380]) == (Slot.LEFT_TOP, 0)
        assert drop_target(Side.LEFT, 400, 40, [20, 60], [380]) == (Slot.LEFT_TOP, 1)
        assert drop_target(Side.LEFT, 400, 150, [20, 60], [380]) == (Slot.LEFT_TOP, 2)
        assert drop_target(Side.LEFT, 400, 390, [20, 60], [380]) == (Slot.LEFT_BOTTOM, 1)
        # an empty group takes drops too
        assert drop_target(Side.BOTTOM, 1000, 900, [100], []) == (Slot.BOTTOM_RIGHT, 0)

    def test_one_open_view_per_place(self):
        layout = _layout()

        assert layout.shown(Slot.BOTTOM_LEFT) == "code"
        # opening the page closes the code, the logs of another place don't
        layout.set_open("logs", True)
        assert layout.others_open("page") == ["code"]
        assert layout.others_open("logs") == []

    def test_a_view_moves_to_another_place_and_within_its_place(self):
        layout = _layout()
        layout.set_open("logs", True)

        # an open view stays open, the open one of its new place closes
        assert layout.move("logs", Slot.BOTTOM_LEFT, 1)
        assert layout.views(Slot.BOTTOM_LEFT) == ["code", "logs", "page"]
        assert layout.open == {"devices", "logs"}

        # within its place: before the view at the index
        assert not layout.move("code", Slot.BOTTOM_LEFT, 3)
        assert layout.views(Slot.BOTTOM_LEFT) == ["logs", "page", "code"]
        assert not layout.move("code", Slot.BOTTOM_LEFT, 0)
        assert layout.views(Slot.BOTTOM_LEFT) == ["code", "logs", "page"]

        # to the end of an empty place
        assert layout.move("page", Slot.RIGHT_BOTTOM)
        assert layout.views(Slot.RIGHT_BOTTOM) == ["page"]

    def test_the_arrangement_survives_the_settings(self):
        layout = _layout()
        layout.move("page", Slot.LEFT_BOTTOM)
        layout.set_open("page", True)
        layout.sizes[Slot.LEFT_BOTTOM] = (280, 300)

        restored = ToolWindowLayout()
        assert restored.load(layout.to_json())
        restored.add("devices", Slot.LEFT_TOP, is_open=True)
        restored.add("code", Slot.BOTTOM_LEFT, is_open=True)
        restored.add("page", Slot.BOTTOM_LEFT)
        restored.add("logs", Slot.BOTTOM_RIGHT)
        # a view that wasn't there before goes to its place, closed or open as it starts
        restored.add("new", Slot.BOTTOM_RIGHT, is_open=True)

        assert restored.views(Slot.LEFT_BOTTOM) == ["page"]
        assert restored.views(Slot.BOTTOM_LEFT) == ["code"]
        assert restored.views(Slot.BOTTOM_RIGHT) == ["logs", "new"]
        assert restored.open == {"devices", "code", "page", "new"}
        assert restored.sizes == {Slot.LEFT_BOTTOM: (280, 300)}

    def test_the_remembered_order_of_a_place(self):
        layout = _layout()
        layout.move("page", Slot.BOTTOM_LEFT, 0)

        restored = ToolWindowLayout()
        restored.load(layout.to_json())
        restored.add("code", Slot.BOTTOM_LEFT)
        restored.add("page", Slot.BOTTOM_LEFT)

        assert restored.views(Slot.BOTTOM_LEFT) == ["page", "code"]

    def test_a_broken_setting_is_ignored(self):
        layout = ToolWindowLayout()

        assert not layout.load({"slots": {"middle": ["code"]}, "open": []})
        assert not layout.load("left")
        layout.add("code", Slot.BOTTOM_LEFT, is_open=True)
        assert layout.views(Slot.BOTTOM_LEFT) == ["code"]

    def test_reset_and_normalize(self):
        layout = _layout()
        layout.move("code", Slot.RIGHT_TOP)
        layout.sizes[Slot.RIGHT_TOP] = (1, 2)

        layout.reset()

        assert layout.views(Slot.BOTTOM_LEFT) == ["code", "page"]
        assert layout.open == {"devices", "code"}
        assert layout.sizes == {}

        # two open views of a place (remembered from another version): the first one stays
        layout.open.add("page")
        layout.normalize()
        assert layout.open == {"devices", "code"}


class TestToolWindowRails(TestBase):
    @staticmethod
    def _shown(window):
        window.resize(1440, 900)
        window.show()
        wait_until(lambda: window.rails.rail(Side.BOTTOM).isVisible())
        # the places got their sizes
        wait_until(lambda: window.rails._sized)
        return window

    @staticmethod
    def _names(rails, side: Side, secondary: bool):
        return [button.dock.objectName() for button in rails.container(side).buttons(secondary)]

    def test_a_button_per_view_in_the_group_of_its_place(self, window):
        # GIVEN
        window = self._shown(window)
        rails = window.rails

        # THEN: every view but the preview has a button
        assert rails.button(window.preview_dock) is None
        assert self._names(rails, Side.LEFT, False) == ["files_dock"]
        assert self._names(rails, Side.LEFT, True) == ["devices_dock"]
        assert self._names(rails, Side.RIGHT, False) == ["properties_dock"]
        assert self._names(rails, Side.RIGHT, True) == ["live_device_dock"]
        assert self._names(rails, Side.BOTTOM, False) == ["jsonl_dock", "page_jsonl_dock"]
        assert self._names(rails, Side.BOTTOM, True) == ["logs_dock"]
        assert rails.button(window.jsonl_dock).isChecked()
        assert not rails.button(window.logs_dock).isChecked()
        # the devices take the room of their rows, the files above them the rest
        devices, files = window.devices_dock, window.files_dock
        wait_until(lambda: devices.isVisible() and files.isVisible() and devices.height() < files.height() / 2)
        assert abs(devices.height() - devices.sizeHint().height()) < 30

    def test_views_of_two_places_are_open_together_and_one_per_place(self, window):
        # GIVEN
        window = self._shown(window)
        rails = window.rails
        code, logs, page = window.jsonl_dock, window.logs_dock, window.page_jsonl_dock

        # WHEN: the logs are opened with their button
        rails.button(logs).click()

        # THEN: next to the code, below the preview
        wait_until(lambda: logs.isVisible() and code.isVisible())
        wait_until(lambda: logs.geometry().x() > code.geometry().right())
        assert abs(logs.geometry().y() - code.geometry().y()) < 5
        assert logs.geometry().y() > window.preview_dock.geometry().bottom()

        # WHEN: the page JSONL of the place of the code is opened from code
        page.show()

        # THEN: the code closes, the logs stay
        assert code.isHidden()
        assert not rails.button(code).isChecked()
        assert rails.button(page).isChecked()
        assert logs.isVisible()

        # WHEN: clicked again, the page JSONL closes
        rails.button(page).click()

        # THEN
        assert page.isHidden()
        assert not rails.button(page).isChecked()

        # WHEN: the logs are closed with the action of the View menu
        logs.toggleViewAction().trigger()

        # THEN
        assert logs.isHidden()
        assert not rails.button(logs).isChecked()

        # WHEN: the default layout is restored
        window.restore_default_layout()

        # THEN
        assert code.isVisible()
        assert rails.button(code).isChecked()

    def test_a_view_moves_to_another_place(self, window):
        # GIVEN
        window = self._shown(window)
        rails = window.rails
        logs = window.logs_dock
        logs.show()

        # WHEN: the logs go below the files, the place of the devices
        rails.move("logs_dock", Slot.LEFT_BOTTOM)

        # THEN: still open, with their button in the second group of the left rail; the devices close
        assert self._names(rails, Side.LEFT, True) == ["devices_dock", "logs_dock"]
        assert "logs_dock" not in self._names(rails, Side.BOTTOM, True)
        assert rails.slot_of(logs) == Slot.LEFT_BOTTOM
        files = window.files_dock
        wait_until(lambda: logs.isVisible() and logs.geometry().y() > files.geometry().bottom())
        assert logs.geometry().right() < window.preview_dock.geometry().x()
        assert files.isVisible()
        assert window.devices_dock.isHidden()
        # the place keeps its size
        height = rails.layout.sizes[Slot.LEFT_BOTTOM][1]
        wait_until(lambda: abs(logs.height() - height) < 10)

        # WHEN: with the context menu of its button, to the place of the code
        menu = rails.menu(logs)
        move_to = next(action.menu() for action in menu.actions() if action.text() == "Move to")
        next(action for action in move_to.actions() if action.text() == "Bottom left").trigger()

        # THEN: the code of its new place closes
        assert rails.slot_of(logs) == Slot.BOTTOM_LEFT
        assert logs.isVisible()
        assert window.jsonl_dock.isHidden()

    def test_the_arrangement_is_remembered(self, create_window):
        # GIVEN
        first = self._shown(create_window())
        first.rails.move("devices_dock", Slot.RIGHT_BOTTOM, 0)
        first.devices_dock.show()

        # WHEN
        first.close()
        second = self._shown(create_window())

        # THEN
        assert second.rails.slot_of(second.devices_dock) == Slot.RIGHT_BOTTOM
        assert self._names(second.rails, Side.RIGHT, True) == ["devices_dock", "live_device_dock"]
        assert second.devices_dock.isVisible()

    def test_a_dock_added_later_gets_a_button(self, window):
        # GIVEN
        from PyQt6.QtWidgets import QLabel

        window = self._shown(window)

        # WHEN: like the docks of the window, but not described for the rails
        dock = window._add_dock("Later", "later_dock", QLabel("later"))

        # THEN: at the bottom left, closed
        wait_until(lambda: window.rails.button(dock) is not None)
        assert window.rails.slot_of(dock) == Slot.BOTTOM_LEFT
        assert window.rails.button(dock).text() == "Later"
        assert dock.isHidden()

        # WHEN: one with a place, open
        other = window._add_dock("Right", "right_dock", QLabel("right"), slot=Slot.RIGHT_BOTTOM, is_open=True)

        # THEN: the live device of its place stays closed
        wait_until(lambda: window.rails.button(other) is not None)
        assert window.rails.side_of(other) == Side.RIGHT
        wait_until(lambda: other.isVisible())

    def test_a_floating_view_keeps_its_place_open(self, window):
        # GIVEN
        window = self._shown(window)
        code, page = window.jsonl_dock, window.page_jsonl_dock

        # WHEN: the code floats, and the page of its place opens
        code.setFloating(True)
        page.show()

        # THEN: both are open
        assert code.isVisible() and page.isVisible()

        # WHEN: the code is docked again
        code.setFloating(False)

        # THEN: it is the open view of its place again
        wait_until(lambda: page.isHidden())
        assert code.isVisible()
        assert window.rails.slot_of(code) == Slot.BOTTOM_LEFT

    def test_the_rails_can_be_hidden(self, window):
        # GIVEN
        window = self._shown(window)
        rail = window.rails.rail(Side.LEFT)
        assert rail.isVisible()

        # WHEN
        window.rails.action_show_rails.setChecked(False)

        # THEN
        assert not rail.isVisible()
