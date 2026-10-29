from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PyQt6.QtGui import QTextFormat  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from openhasp_config_manager.gui.domain.problems import Severity  # noqa: E402
from openhasp_config_manager.gui.domain.source.syntax import Language  # noqa: E402
from openhasp_config_manager.gui.domain.variables.definitions import Definition  # noqa: E402
from openhasp_config_manager.gui.domain.source.issues import SourceIssue  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.code_editor.editor import CodeEditor  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.code_editor import hover as editor_hover  # noqa: E402
from tests import TestBase  # noqa: E402
from tests.gui.helpers import wait_until  # noqa: E402
from tests.gui.code_editor.helpers import _type


class TestLinksAndDocs(TestBase):
    def test_ctrl_click_on_a_reference(self, qapp, settings):
        editor = CodeEditor(Language.CMD)
        editor.resize(500, 100)
        editor.show()
        editor.set_text("run L:/pages.jsonl\nrun x")
        targets = []
        editor.linkRequested.connect(targets.append)
        position = QPoint(editor.fontMetrics().horizontalAdvance("run L:/pa") + 5, 5)

        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, position)
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, position)
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, QPoint(5, 30))

        assert targets == ["pages.jsonl"]
        editor.close()

    def test_ctrl_click_on_a_part_of_a_variable(self, qapp, settings):
        # GIVEN: only `common.header` is defined
        editor = CodeEditor(Language.JSONL)
        editor.resize(500, 100)
        editor.show()
        editor.set_text('{"h": "{{ common.header.height }}"}')
        known = {"common", "common.header"}
        editor.set_definition_finder(lambda name: Definition(Path("x.yaml"), 1, 0) if name in known else None)
        names = []
        editor.definitionRequested.connect(names.append)
        click = Qt.KeyboardModifier.ControlModifier

        # WHEN
        for prefix in ('{"h": "{{ com', '{"h": "{{ common.hea', '{"h": "{{ common.header.hei'):
            position = QPoint(editor.fontMetrics().horizontalAdvance(prefix) + 2, 5)
            QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, click, position)

        # THEN: the last part has no definition
        assert names == ["common", "common.header"]
        editor.close()

    def test_hovering_with_ctrl_underlines_the_reference(self, qapp, settings):
        editor = CodeEditor(Language.CMD)
        editor.resize(500, 100)
        editor.show()
        editor.set_text("run L:/pages.jsonl")
        position = QPoint(editor.fontMetrics().horizontalAdvance("run L:/pa") + 5, 5)
        before = len(editor.extraSelections())

        QTest.mouseMove(editor.viewport(), position)
        editor._set_hover_link(editor._link_at(position))
        assert len(editor.extraSelections()) == before + 1
        assert editor.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor
        QTest.keyRelease(editor, Qt.Key.Key_Control)
        assert len(editor.extraSelections()) == before
        assert editor.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor
        editor.close()

    def _position(self, editor, prefix: str, line: int = 0) -> QPoint:
        # the line height of the editor is not the height of its font (it depends on the font of the machine)
        block = editor.blockBoundingGeometry(editor.document().findBlockByNumber(line)).translated(editor.contentOffset())
        return QPoint(editor.fontMetrics().horizontalAdvance(prefix) + 6, int(block.center().y()))

    def _hover(self, editor, position: QPoint):
        # the cursor of the test platform stays where it was, so moving to the same place twice sends no event
        QTest.mouseMove(editor.viewport(), QPoint(450, 250))
        QTest.mouseMove(editor.viewport(), position)

    def test_the_current_line_does_not_hide_the_color_of_a_color_string(self, qapp, settings):
        # GIVEN: a color string in the line of the cursor: it is shown on its color (white), with dark text
        editor = CodeEditor(Language.YAML)
        editor.resize(400, 100)
        editor.show()
        editor.set_text('c: "#ffffff"\n')
        editor.go_to(1, 0)
        qapp.processEvents()

        # WHEN
        image = editor.viewport().grab().toImage()

        # THEN: the string still has its light background, not the dark one of the editor
        block = editor.blockBoundingGeometry(editor.document().firstBlock()).translated(editor.contentOffset())
        x = editor.fontMetrics().horizontalAdvance('c: "#fff') + editor.document().documentMargin()
        assert image.pixelColor(int(x), int(block.top() + 1)).lightness() > 150
        editor.close()

    def test_a_hint_dims_the_text_but_not_a_color_string(self, qapp, settings):
        # GIVEN: an unused variable (a hint) with a color: dimmed text would be white on the white color
        editor = CodeEditor(Language.YAML)
        editor.set_text('  text_color: "#E8EAF0"\n')
        editor.set_hints([SourceIssue(1, 2, 22, Severity.HINT, "unused")])

        # THEN: the key is dimmed, the color string is not
        dimmed = {
            (selection.cursor.selectionStart(), selection.cursor.selectionEnd()): selection.format.hasProperty(
                QTextFormat.Property.ForegroundBrush
            )
            for selection in editor.extraSelections()
        }
        assert dimmed == {(2, 14): True, (14, 23): False}

    def test_hover_card_explains_a_placeholder(self, editor):
        editor.set_text('{"obj": "btn", "text": "%ip%"}')

        content = editor.hover.card_content_at(self._position(editor, '{"obj": "btn", "text": "%i'))

        assert content.help is not None and content.help.name == "%ip%"
        assert "IP address" in content.help.summary
        assert content.help.url == "https://www.openhasp.com/0.7.0/design/data-types/#variables"

    def test_placeholder_has_its_own_color(self, editor):
        from openhasp_config_manager.gui.domain.source.syntax import TokenKind
        from openhasp_config_manager.gui.qt.widgets.code_editor.highlighter import syntax_color

        editor.set_text('{"text": "%ip%"}')
        formats = editor.document().firstBlock().layout().formats()
        color_at = {f.start: f.format.foreground().color() for f in formats}
        assert color_at[len('{"text": "')] == syntax_color(TokenKind.PLACEHOLDER)
        assert syntax_color(TokenKind.PLACEHOLDER) not in (syntax_color(TokenKind.STRING), syntax_color(TokenKind.TEMPLATE))

    def test_hover_card_explains_the_default_properties_of_the_theme(self, qapp, settings):
        yaml_editor = CodeEditor(Language.YAML)
        yaml_editor.resize(500, 200)
        yaml_editor.show()
        yaml_editor.set_text("theme:\n  obj:\n    btn:\n      bg_color04: '#fff'\n")

        content = yaml_editor.hover.card_content_at(self._position(yaml_editor, "      bg_", line=3))

        assert content.help is not None and content.help.name == "bg_color04"
        yaml_editor.close()

    def test_pressing_ctrl_keeps_the_hover_card_so_its_text_can_be_copied(self, editor):
        # GIVEN: the card is shown
        editor.set_text('{"w": "33%"}')
        self._hover(editor, self._position(editor, '{"'))
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=2 * editor_hover._HOVER_DELAY_MS + 400)

        # WHEN: Ctrl is pressed in the card (which has the focus after text was selected), and in the editor
        QTest.keyPress(editor.hover.card._body, Qt.Key.Key_Control)
        QTest.keyPress(editor, Qt.Key.Key_Control)

        # THEN
        assert editor.hover.card.isVisible()

        # WHEN: a key that is input
        QTest.keyClick(editor, Qt.Key.Key_X)

        # THEN: the card is gone
        assert not editor.hover.card.isVisible()

    def test_hover_card_shows_after_a_short_delay(self, editor):

        editor.set_text('{"w": "33%"}')
        self._hover(editor, self._position(editor, '{"'))
        assert editor_hover._HOVER_DELAY_MS <= 150
        assert not editor.hover.card.isVisible()
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=2 * editor_hover._HOVER_DELAY_MS + 400)
        assert editor.hover.card._name.text() == "w" and "pixels" in editor.hover.card._body.toPlainText()
        assert editor.hover.card._kind.text() == "Property of every object"
        assert "openhasp.com" in editor.hover.card._link.text()

    def _card_and_property(self, editor, line: int):
        """:return: the rectangles of the card and of the property it is about, in the coordinates of the editor"""
        self._hover(editor, self._position(editor, '{"', line))
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=1000)
        area = editor.hover.tip_area
        return editor.hover.card.geometry(), QRect(editor.viewport().mapTo(editor, area.topLeft()), area.size())

    def test_hover_card_is_above_the_property(self, editor):
        editor.resize(600, 700)
        editor.set_text("\n" * 14 + '{"w": "33%"}')
        card, area = self._card_and_property(editor, 14)
        assert card.bottom() < area.top()
        assert editor.rect().contains(card)

    def test_hover_card_is_below_if_there_is_no_room_above(self, editor):
        editor.resize(600, 700)
        editor.set_text('{"w": "33%"}')
        card, area = self._card_and_property(editor, 0)
        assert card.top() > area.bottom()
        assert editor.rect().contains(card)

    def test_hover_card_never_covers_the_property(self, editor):
        # an editor that is too small for the card above or below: the text of the card gets shorter
        editor.resize(600, 160)
        editor.set_text("\n" * 3 + '{"obj": "switch", "bg_color10": "x"}')
        card, area = self._card_and_property(editor, 3)
        assert not card.intersects(area)

    def test_hover_card_is_not_a_window(self, editor):
        assert not editor.hover.card.isWindow() and editor.hover.card.parentWidget() is editor
        assert not editor.completion.card.isWindow()

    def test_hover_card_stays_while_the_mouse_is_on_it(self, editor):

        editor.set_text('{"w": "33%"}')
        self._hover(editor, self._position(editor, '{"'))
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=1000)
        # the mouse leaves the editor and reaches the card in time
        editor.hover.grace_timer.start()
        editor.hover.card.mouseEntered.emit()
        QTest.qWait(editor_hover._HOVER_GRACE_MS + 100)
        assert editor.hover.card.isVisible()
        # and leaves the card
        editor.hover.card.mouseLeft.emit()
        wait_until(lambda: not editor.hover.card.isVisible(), timeout_ms=editor_hover._HOVER_GRACE_MS + 500)

    def test_hover_card_goes_away_after_the_mouse_left_the_property(self, editor):

        editor.set_text('{"w": "33%", "h": 1}')
        self._hover(editor, self._position(editor, '{"'))
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=1000)
        self._hover(editor, QPoint(490, 290))
        wait_until(lambda: not editor.hover.card.isVisible(), timeout_ms=editor_hover._HOVER_GRACE_MS + 500)

    def test_hover_card_moves_to_the_next_property(self, editor):
        editor.set_text('{"w": "33%", "h": 1}')
        self._hover(editor, self._position(editor, '{"'))
        wait_until(lambda: editor.hover.card.isVisible() and editor.hover.card._name.text() == "w", timeout_ms=1000)
        self._hover(editor, self._position(editor, '{"w": "33%", "h'))
        wait_until(lambda: editor.hover.card._name.text() == "h", timeout_ms=1000)
        assert editor.hover.card.isVisible()

    def test_hover_card_goes_away_when_typing_or_clicking(self, editor):
        editor.set_text('{"w": "33%"}')
        for action in (
            lambda: QTest.keyClick(editor, Qt.Key.Key_End),
            lambda: QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(300, 100)),
        ):
            self._hover(editor, self._position(editor, '{"'))
            wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=1000)
            action()
            assert not editor.hover.card.isVisible()

    def test_card_content_of_a_property(self, editor):
        text = '{"w": "33%", "nope": 1, "bg_color02": "x"}'
        editor.set_text(text)

        def at(prefix: str):
            return editor.hover.card_content_at(self._position(editor, prefix))

        assert at('{"').help.name == "w" and "pixels" in at('{"').help.summary
        assert at('{"w": "33%", "no').is_empty()  # unknown property
        assert at('{"w": "33%').is_empty()  # a value
        editor.set_text('{"src": "x", "text_color02": 1}')
        assert "`L:/image.png`" in at('{"sr').help.summary
        found = at('{"src": "x", "text_c').help
        assert found.name == "text_color02" and dict(found.details)["State"] == "2: pressed, not toggled"
        editor.set_text('{"obj": "switch", "bg_color10": 1}')
        assert dict(at('{"obj": "switch", "bg_c').help.details)["Part"] == "1: the indicator (the colored track)"
        editor.set_text("run x")
        assert at("ru").is_empty()

    def test_card_content_of_a_variable_is_its_value(self, editor):
        editor.set_text('{"h": "{{ header.height }}"}')
        editor.values.set_source(lambda name: 44 if name == "header.height" else {"height": 44}, lambda text: "44")

        found = editor.hover.card_content_at(self._position(editor, '{"h": "{{ header.he')).help
        assert (found.name, found.summary) == ("header.height", "`44`")
        assert editor.hover.card_content_at(self._position(editor, '{"h": "{{ hea')).help.summary == "`{height}`"

    def test_values_are_shown_after_the_line_when_asked_for(self, editor):
        editor.resize(600, 200)
        editor.show()
        editor.set_text('{"h": "{{ header.height }}"}\n{"x": 1}')
        calls = []
        editor.values.set_source(lambda name: 44, lambda text: calls.append(text) or "44")

        # on: the templates of the visible lines, once (until the values are refreshed)
        editor.values.set_show(True)
        editor.grab()
        editor.grab()
        assert calls == ["{{ header.height }}"]
        editor.values.refresh()
        editor.grab()
        assert calls == ["{{ header.height }}"] * 2

    def test_card_shows_issues_with_the_explanation(self, editor):
        editor.set_text('{"w": "33%"}')
        editor.set_app_markers([SourceIssue(1, 1, 3, Severity.ERROR, "Broken")])
        content = editor.hover.card_content_at(self._position(editor, '{"'))
        assert content.issues == [(Severity.ERROR, "Broken")] and content.help.name == "w"
        self._hover(editor, self._position(editor, '{"'))
        wait_until(lambda: editor.hover.card.isVisible(), timeout_ms=1000)
        assert "Broken" in editor.hover.card._issues.text()


class TestDirectives(TestBase):
    def _colors(self, editor, line: int):
        """:return: (text, color) of the highlighted ranges of a line"""
        block = editor.document().findBlockByNumber(line - 1)
        return [
            (block.text()[fmt.start : fmt.start + fmt.length], fmt.format.foreground().color().name())
            for fmt in block.layout().formats()
        ]

    def test_the_keys_of_a_directive_have_their_own_color(self, editor):
        from openhasp_config_manager.gui.domain.source.syntax import TokenKind
        from openhasp_config_manager.gui.qt.widgets.code_editor.highlighter import syntax_color

        # WHEN
        editor.set_text('{\n  "!include": "a.jsonl",\n  "vars": {"vars": 1}\n}\n{"vars": 1}')

        # THEN
        directive, key = syntax_color(TokenKind.DIRECTIVE).name(), syntax_color(TokenKind.KEY).name()
        assert ('"!include"', directive) in self._colors(editor, 2)
        # the key of the directive, and a variable named like it
        assert self._colors(editor, 3)[0] == ('"vars"', directive)
        assert ('"vars"', key) in self._colors(editor, 3)
        assert ('"vars"', key) in self._colors(editor, 5)

        # WHEN: the directive goes away, the lines after it are colored again
        cursor = editor.textCursor()
        cursor.setPosition(editor.document().findBlockByNumber(1).position() + 3)
        cursor.insertText("x")

        # THEN
        assert self._colors(editor, 3)[0] == ('"vars"', key)

    def test_the_path_of_an_include_is_completed(self, editor):
        # GIVEN
        editor.completion.set_include_paths(lambda: ["common/parts/tile.jsonl", "common/page.jsonl"])

        # WHEN
        _type(editor, '{"!include": "common/pa')

        # THEN
        assert editor.completion.completer.popup().isVisible()
        assert editor.completion.completer.model().stringList() == ["common/page.jsonl", "common/parts/tile.jsonl"]
        QTest.keyClick(editor.completion.completer.popup(), Qt.Key.Key_Down)
        QTest.keyClick(editor.completion.completer.popup(), Qt.Key.Key_Return)
        assert editor.toPlainText().startswith('{"!include": "common/parts/tile.jsonl"')

    def test_a_directive_offers_its_keys_with_their_explanation(self, editor):
        # GIVEN
        editor.resize(900, 400)
        editor.set_text('{"!include": "a.jsonl", "')
        editor.go_to(1, 25)

        # WHEN
        QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)

        # THEN
        assert editor.completion.completer.model().stringList() == ["for", "vars"]
        assert editor.completion.card._kind.text() == "Key of an `!include`"

    def test_ctrl_click_on_the_path_of_an_include(self, editor):
        # GIVEN
        editor.set_text('{"!include": "common/parts/tile.jsonl"}')
        paths = []
        editor.includeRequested.connect(paths.append)
        position = QPoint(editor.fontMetrics().horizontalAdvance('{"!include": "common/pa') + 2, 5)

        # WHEN
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, position)

        # THEN
        assert paths == ["common/parts/tile.jsonl"]
