from pathlib import Path

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

    def test_label_text_starts_at_the_top_whatever_the_height(self):
        # GIVEN
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.label import HaspLabelItem

        label = HaspLabelItem(obj_data={"obj": "label", "x": 0, "y": 0, "w": 100, "h": 20, "text": "Desk"})

        # WHEN
        label.obj_data["h"] = 60
        label.refresh()

        # THEN the text is at the top, below the pixels a line has above its glyphs on the plate
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import line_top

        assert label.text_item.pos().y() == line_top(label.text_item.font())

    def test_label_text_has_no_margin_around_it(self):
        # GIVEN
        from PyQt6 import QtGui

        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.label import HaspLabelItem

        # WHEN
        label = HaspLabelItem(obj_data={"obj": "label", "x": 0, "y": 0, "w": 200, "h": 30, "text": "Desk", "text_font": 25})

        # THEN the text is as tall as its line (and the lead of the plate), not 8px taller (Qt's default margin)
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.drawing import line_lead

        text_item = label.text_item
        assert (
            text_item.boundingRect().height()
            < QtGui.QFontMetricsF(text_item.font()).height() + line_lead(text_item.font()) + 1
        )

    def test_switch_value_and_position_follow_its_data(self):
        # GIVEN
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.switch import HaspSwitchItem

        switch = HaspSwitchItem(obj_data={"obj": "switch", "x": 0, "y": 0, "w": 80, "h": 40, "val": 0})

        # WHEN
        switch.obj_data.update(val=1, x=25)
        switch.refresh()

        # THEN
        assert switch.is_toggled
        assert switch.pos().x() == 25

    def test_style_reads_the_property_of_a_part(self):
        from openhasp_config_manager.gui.domain.style_parts import Part
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.switch import HaspSwitchItem

        switch = HaspSwitchItem(obj_data={"obj": "switch", "radius": 3, "bg_color20": "red", "bg_color": "blue"})

        assert switch.style("radius") == 3
        assert switch.style("bg_color", part=Part.KNOB) == "red"
        assert switch.style("bg_color") == "blue"
        assert switch.style("bg_color", "x", Part.INDICATOR) == "x"


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


@pytest.mark.usefixtures("qapp")
class TestImageItem(TestBase):
    @staticmethod
    def _paint(item, width, height, offset=0):
        from PyQt6.QtGui import QImage, QPainter

        canvas = QImage(width, height, QImage.Format.Format_ARGB32)
        canvas.fill(0xFF000000)
        painter = QPainter(canvas)
        painter.translate(offset, offset)
        item.paint(painter, None)
        painter.end()
        return canvas

    @staticmethod
    def _item(tmp_path, name, content: bytes, **props):
        from openhasp_config_manager.gui.domain.interaction import RuntimeState
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.image import HaspImageItem

        class Preview:
            runtime = RuntimeState()

            def image_file(self, src):
                return Path(tmp_path, name) if src.endswith(name) else None

        Path(tmp_path, name).write_bytes(content)
        return HaspImageItem(
            obj_data={"obj": "img", "x": 0, "y": 0, "w": 4, "h": 4, "src": f"L:/{name}", **props}, parent_widget=Preview()
        )

    def test_outline_is_drawn_outside_of_the_object(self, tmp_path):
        from tests.png import png

        item = self._item(
            tmp_path, "a.png", png((4, 4), [(0, 255, 0)] * 16), outline_width=2, outline_pad=1, outline_color="#ff0000"
        )

        canvas = self._paint(item, 14, 14, offset=5)

        # the image is inside, then 1 px gap, then the ring of 2 px
        assert canvas.pixelColor(6, 6).green() == 255
        assert canvas.pixelColor(4, 6).red() == 0
        assert canvas.pixelColor(3, 6).red() == 255
        assert canvas.pixelColor(2, 6).red() == 255
        assert canvas.pixelColor(1, 6).red() == 0
        assert item.boundingRect().left() <= -5

    def test_no_outline_without_a_width(self, tmp_path):
        from tests.png import png

        item = self._item(tmp_path, "a.png", png((4, 4), [(0, 255, 0)] * 16), outline_color="#ff0000")

        canvas = self._paint(item, 14, 14, offset=5)

        assert canvas.pixelColor(4, 6).red() == 0

    def test_placeholder_has_the_radius_of_the_object(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.image import HaspImageItem

        item = HaspImageItem(obj_data={"obj": "img", "x": 0, "y": 0, "w": 20, "h": 20, "src": "http://x/a.png", "radius": 10})

        canvas = self._paint(item, 20, 20)

        assert canvas.pixelColor(0, 0).red() == 0
        assert canvas.pixelColor(10, 3).red() == 255

    def test_png_is_drawn_in_its_size_and_cut_off_by_the_object(self, tmp_path):
        from tests.png import png

        item = self._item(tmp_path, "a.png", png((6, 2), [(255, 0, 0)] * 12), w=4, h=4)

        canvas = self._paint(item, 8, 8)

        assert canvas.pixelColor(3, 1).red() == 255
        # below the image and right of the object
        assert canvas.pixelColor(3, 3).red() == 0
        assert canvas.pixelColor(5, 1).red() == 0

    def test_binary_image_keeps_transparent_pixels_and_ignores_zoom(self, tmp_path):
        from openhasp_config_manager.processing.image_conversion import png_to_binary
        from tests.png import png

        content = png_to_binary(png((2, 1), [(0, 0, 255, 255), (255, 255, 255, 0)], mode="RGBA"))
        item = self._item(tmp_path, "a.bin", content, zoom=512)

        canvas = self._paint(item, 8, 8)

        assert canvas.pixelColor(0, 0).blue() == 255
        # transparent: the canvas shows through
        assert canvas.pixelColor(1, 0).blue() == 0
        assert canvas.pixelColor(2, 0).blue() == 0

    def test_png_follows_its_zoom(self, tmp_path):
        from tests.png import png

        item = self._item(tmp_path, "a.png", png((2, 2), [(255, 0, 0)] * 4), zoom=512)

        canvas = self._paint(item, 8, 8)

        # like on the plate it is scaled around its middle: 4 x 4 pixels around (1, 1)
        assert canvas.pixelColor(0, 0).red() == 255
        assert canvas.pixelColor(2, 2).red() == 255
        assert canvas.pixelColor(3, 3).red() == 0

    def test_file_that_can_not_be_read_shows_the_placeholder(self, tmp_path):
        # big and without a radius, so the corner is the color and the "IMG" text in the middle is not in the way
        item = self._item(tmp_path, "a.bin", b"not an image", bg_color="#00ff00", w=20, h=20, radius=0)

        assert item.image is None
        assert self._paint(item, 24, 24).pixelColor(1, 1).green() == 255

    def test_image_from_a_url_shows_the_placeholder(self):
        from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.image import HaspImageItem

        item = HaspImageItem(
            obj_data={"obj": "img", "x": 0, "y": 0, "w": 4, "h": 4, "src": "http://host/a"}, parent_widget=None
        )

        assert item.image is None

    def test_data_change_reloads_the_image(self, tmp_path):
        from tests.png import png

        item = self._item(tmp_path, "a.png", png((1, 1), [(255, 0, 0)]))
        assert item.image is not None
        item.obj_data["src"] = "L:/missing.png"
        item.refresh()

        assert item.image is None
