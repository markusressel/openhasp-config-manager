import pytest

from tests import TestBase


@pytest.mark.usefixtures("qapp")
class TestOpenHaspWidgets(TestBase):
    def test_button_text_follows_its_data(self):
        # GIVEN
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.button import HaspButtonItem

        button = HaspButtonItem(obj_data={"obj": "btn", "x": 0, "y": 0, "w": 100, "h": 40, "text": "Work"})

        # WHEN
        button.obj_data["text"] = "Sleep"
        button.refresh()

        # THEN
        assert button.text_item.toPlainText() == "Sleep"

    def test_label_text_can_become_empty(self):
        # GIVEN
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.label import HaspLabelItem

        label = HaspLabelItem(obj_data={"obj": "label", "x": 0, "y": 0, "w": 100, "h": 40, "text": "Desk"})

        # WHEN
        label.obj_data["text"] = ""
        label.refresh()

        # THEN
        assert label.text_item.toPlainText() == ""

    def test_switch_value_and_position_follow_its_data(self):
        # GIVEN
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.switch import HaspSwitchItem

        switch = HaspSwitchItem(obj_data={"obj": "switch", "x": 0, "y": 0, "w": 80, "h": 40, "val": 0})

        # WHEN
        switch.obj_data.update(val=1, x=25)
        switch.refresh()

        # THEN
        assert switch._val == 1
        assert switch.pos().x() == 25


@pytest.mark.usefixtures("qapp")
class TestTemplateCompleter(TestBase):
    def test_suggestion_html_highlights_matched_characters_and_escapes(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.template_completer import suggestion_html

        result = suggestion_html("{{ a<b }}", [3, 5], "'x'", match_color="#ff0000", value_color="#888")

        assert result.startswith('{{ <b style="color: #ff0000;">a</b>&lt;<b style="color: #ff0000;">b</b> }}')
        assert result.endswith('<span style="color: #888;">= &#x27;x&#x27;</span>')
