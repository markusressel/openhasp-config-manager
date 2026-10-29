
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from openhasp_config_manager.gui.domain.source.syntax import Language  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.code_editor.editor import CodeEditor  # noqa: E402
from tests import TestBase  # noqa: E402
from tests.gui.helpers import wait_until  # noqa: E402
from tests.gui.code_editor.helpers import _type


class TestColorSwatches(TestBase):
    def test_colors_of_a_line_are_its_color_strings_and_templates_rendering_to_colors(self, editor):
        editor.set_text('{"bg_color": "#FF0000", "text_color": "{{ c }}"}\n{"x": 1}')
        editor.values.set_source(lambda name: None, lambda text: "#00FF00")

        assert [color.hex() for color in editor.values.colors_of(editor.document().findBlockByNumber(0).text())] == [
            "#FF0000",
            "#00FF00",
        ]
        assert editor.values.colors_of(editor.document().findBlockByNumber(1).text()) == []

    def test_swatches_are_painted_in_the_gutter(self, editor):
        editor.resize(600, 200)
        editor.show()
        editor.set_text('{"bg_color": "#FF0000"}')

        image = editor.gutter.grab().toImage()

        assert any(
            image.pixelColor(x, y).red() > 200 and image.pixelColor(x, y).green() < 60
            for x in range(image.width())
            for y in range(20)
        )


class TestFlash(TestBase):
    def test_lines_are_highlighted_for_a_moment(self, editor):
        # GIVEN
        editor.set_text('{\n  "page": 1,\n  "id": 2\n}\n')

        # WHEN
        editor.flash_lines(1, 4, duration_ms=50)

        # THEN
        assert editor.flashed_lines == (1, 4)
        assert sum(s.format.background().color().alpha() > 0 for s in editor.extraSelections()) >= 4
        # a slow machine (CI) may need longer than the duration
        wait_until(lambda: editor.flashed_lines is None)

    def test_typing_clicking_or_a_reload_end_the_highlight(self, editor):
        # GIVEN
        editor.set_text('{"page": 1}\n')

        # WHEN / THEN
        editor.flash_lines(1, 1)
        _type(editor, "x")
        assert editor.flashed_lines is None

        editor.flash_lines(1, 1)
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
        assert editor.flashed_lines is None

        editor.flash_lines(1, 1)
        editor.set_text('{"page": 2}\n')
        assert editor.flashed_lines is None


class TestColorPicker(TestBase):
    def _editor(self, language=Language.JSONL, text='{"c": "#0D0F14", "d": 1}'):
        editor = CodeEditor(language)
        editor.resize(500, 300)
        editor.show()
        editor.set_text(text)
        return editor

    def _color(self, editor, prefix='{"c": "#0D'):
        position = QPoint(editor.fontMetrics().horizontalAdvance(prefix) + 2, 5)
        return editor._colors.color_at(position)

    def test_finds_the_color_under_the_mouse(self, qapp, settings):
        editor = self._editor()
        number, token = self._color(editor)
        assert (number, token.start, token.end) == (0, 6, 15)
        assert self._color(editor, '{"c"') is None
        editor.close()

    def test_ctrl_click_opens_the_picker_and_edits_the_text(self, qapp, settings):
        # GIVEN
        editor = self._editor()
        edits = []
        editor.textEdited.connect(lambda: edits.append(1))
        position = QPoint(editor.fontMetrics().horizontalAdvance('{"c": "#0D') + 2, 5)

        # WHEN
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, position)
        assert editor._picker.isVisible()
        editor._picker.set_color(255, 0, 0, 255)
        editor._picker.set_color(0, 128, 255, 255)

        # THEN: the quotes and the case stay, the rest of the line is untouched
        assert editor.toPlainText() == '{"c": "#0080FF", "d": 1}'
        assert edits

        # WHEN: closed, the changes are one step to undo
        editor._picker.close_picker()
        editor.undo()
        assert editor.toPlainText() == '{"c": "#0D0F14", "d": 1}'
        editor.close()

    def test_the_style_of_the_color_is_kept(self, qapp, settings):
        editor = self._editor(Language.YAML, "color: '#0d0f14'")
        editor.edit_color(*self._color_at_start(editor))
        editor._picker.set_color(1, 2, 255, 255)
        assert editor.toPlainText() == "color: '#0102ff'"

        # an alpha other than 255 makes it #AARRGGBB
        editor._picker.set_color(1, 2, 255, 128)
        assert editor.toPlainText() == "color: '#800102ff'"
        editor._picker.set_color(1, 2, 255, 255)
        assert editor.toPlainText() == "color: '#0102ff'"
        editor.close()

    def _color_at_start(self, editor):
        return editor._colors.color_at(QPoint(editor.fontMetrics().horizontalAdvance("color: '#0") + 2, 5))

    def test_the_text_of_the_picker_follows_typing(self, qapp, settings):
        editor = self._editor()
        editor.edit_color(*self._color(editor))
        picker = editor._picker
        picker._text.textEdited.emit("#336699")
        assert editor.toPlainText() == '{"c": "#336699", "d": 1}'
        assert [picker._channels[name].value() for name in "ARGB"] == [255, 51, 102, 153]

        # not a color yet: nothing changes
        picker._text.textEdited.emit("#33")
        assert editor.toPlainText() == '{"c": "#336699", "d": 1}'
        editor.close()

    def test_the_wheel_changes_the_color(self, qapp, settings):
        editor = self._editor(text='{"c": "#FF0000"}')
        editor.edit_color(*self._color(editor, '{"c": "#F'))
        wheel = editor._picker._wheel
        assert wheel.hue == 0 and wheel.saturation == 1.0 and wheel.value == 1.0

        wheel.hue = 120
        wheel.changed.emit()
        assert editor.toPlainText() == '{"c": "#00FF00"}'
        editor.close()

    def test_escape_closes_the_picker(self, qapp, settings):
        editor = self._editor()
        editor.edit_color(*self._color(editor))
        QTest.keyClick(editor._picker, Qt.Key.Key_Escape)
        assert not editor._picker.isVisible()
        assert editor._colors._edit is None
        editor.close()
