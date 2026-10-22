import pytest

from tests import TestBase


@pytest.mark.usefixtures("qapp")
class TestOpenHaspWidgets(TestBase):
    def test_button_text_follows_its_data(self):
        # GIVEN
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.button import HaspButtonItem

        button = HaspButtonItem(obj_data={"obj": "btn", "x": 0, "y": 0, "w": 100, "h": 40, "text": "Work"})

        # WHEN
        button.set_property("text", "Sleep")

        # THEN
        assert button.text_item.toPlainText() == "Sleep"

    def test_label_text_can_become_empty(self):
        # GIVEN
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.label import HaspLabelItem

        label = HaspLabelItem(obj_data={"obj": "label", "x": 0, "y": 0, "w": 100, "h": 40, "text": "Desk"})

        # WHEN
        label.set_property("text", "")

        # THEN
        assert label.text_item.toPlainText() == ""

    def test_switch_value_and_position_follow_its_data(self):
        # GIVEN
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.switch import HaspSwitchItem

        switch = HaspSwitchItem(obj_data={"obj": "switch", "x": 0, "y": 0, "w": 80, "h": 40, "val": 0})

        # WHEN
        switch.set_property("val", 1)
        switch.set_property("x", 25)

        # THEN
        assert switch._val == 1
        assert switch.pos().x() == 25
