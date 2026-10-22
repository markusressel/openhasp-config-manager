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


@pytest.mark.usefixtures("qapp")
class TestPagePreviewWidget(TestBase):
    def _click(self, preview, scene_x: float, scene_y: float):
        from PyQt6 import QtCore
        from PyQt6.QtTest import QTest

        point = preview.mapFromScene(QtCore.QPointF(scene_x, scene_y))
        QTest.mouseClick(preview.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)

    def test_click_in_interact_mode_starts_a_ripple_on_the_plate_only(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget, PreviewMode

        preview = PagePreviewWidget()
        preview.resize(600, 400)
        preview.set_mode(PreviewMode.Interact)
        preview.fit_to_view()

        self._click(preview, 100, 100)
        # outside of the plate
        self._click(preview, -100, -100)

        assert [(round(r.x), round(r.y)) for r in preview._ripples] == [(100, 100)]
        assert preview._ripple_timer.isActive()

    def test_fast_clicks_start_one_ripple_each(self):
        from PyQt6 import QtCore
        from PyQt6.QtTest import QTest

        from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget, PreviewMode

        preview = PagePreviewWidget()
        preview.resize(600, 400)
        preview.set_mode(PreviewMode.Interact)
        preview.fit_to_view()

        point = preview.mapFromScene(QtCore.QPointF(100, 100))
        QTest.mouseClick(preview.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)
        # the second click of a double click is a double click event, not a press
        QTest.mouseDClick(preview.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)

        assert len(preview._ripples) == 2

    def test_no_ripple_in_edit_mode(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget, PreviewMode

        preview = PagePreviewWidget()
        preview.resize(600, 400)
        preview.set_mode(PreviewMode.Edit)
        preview.fit_to_view()

        self._click(preview, 100, 100)

        assert preview._ripples == []

    @pytest.mark.parametrize("size", [(900, 600), (320, 600)])
    def test_the_fitted_plate_is_fully_visible_and_not_covered_by_the_floating_bars(self, size):
        # GIVEN
        from PyQt6.QtWidgets import QPushButton

        from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import OverlayAnchor, PagePreviewWidget

        preview = PagePreviewWidget()
        preview.set_screen_size(480, 320)
        bars = [QPushButton("Edit mode  Snap  Duplicate"), QPushButton("‹ Page 1 ›"), QPushButton("− fit +")]
        for bar, anchor in zip(bars, [OverlayAnchor.TOP_RIGHT, OverlayAnchor.BOTTOM_CENTER, OverlayAnchor.BOTTOM_RIGHT]):
            preview.add_overlay(bar, anchor)
        preview.resize(*size)
        preview.show()

        # WHEN
        preview.fit_to_view()

        # THEN
        plate = preview.mapFromScene(preview.scene().sceneRect()).boundingRect()
        assert preview.viewport().rect().contains(plate)
        for bar in bars:
            assert preview.viewport().rect().contains(bar.geometry())
            assert not bar.geometry().intersects(plate)

    def test_cursor_plate_position_is_on_the_grid_and_only_over_the_plate(self):
        # GIVEN
        from PyQt6 import QtCore
        from PyQt6.QtGui import QCursor

        from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget

        preview = PagePreviewWidget()
        preview.set_screen_size(480, 320)
        preview.resize(600, 400)
        preview.show()
        preview.fit_to_view()

        def at(scene_x: float, scene_y: float):
            QCursor.setPos(preview.viewport().mapToGlobal(preview.mapFromScene(QtCore.QPointF(scene_x, scene_y))))
            return preview.cursor_plate_position()

        # WHEN / THEN
        grid = preview.scene().grid_size
        assert at(3 * grid + 1, 2 * grid - 1) == (3 * grid, 2 * grid)
        assert at(-20, 10) is None
        preview.set_snap_enabled(False)
        x, y = at(101, 53)
        # off the grid, up to the rounding of the zoomed view
        assert abs(x - 101) <= 1 and abs(y - 53) <= 1
