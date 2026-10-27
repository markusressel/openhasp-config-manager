import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QSettings, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QMessageBox, QWidget  # noqa: E402

from openhasp_config_manager.gui.domain.problems import Severity  # noqa: E402
from openhasp_config_manager.gui.domain.source_buffers import DiskChange  # noqa: E402
from openhasp_config_manager.gui.domain.source_issues import SourceIssue  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.code_view import CodeView, CodeViewMode  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.source_editor import SourceEditorWidget  # noqa: E402
from tests import TestBase  # noqa: E402


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "a.jsonl").write_text('{"page": 1, "id": 1}\n{"page": 1, "id": 2}\n')
    (tmp_path / "b.jsonl").write_text('{"page": 2, "id": 1}\n')
    (tmp_path / "vars.yaml").write_text("a: 1\n")
    return tmp_path


@pytest.fixture
def widget(qapp, settings, folder):
    widget = SourceEditorWidget(folder)
    widget.resize(600, 400)
    widget.show()
    yield widget
    widget.close_all(ask=False)
    widget.close()


def _type(widget, text):
    QTest.keyClicks(widget.current_editor, text)


class TestOpen(TestBase):
    def test_nothing_is_open_at_first(self, widget):
        assert widget.open_files == []
        assert widget.current_file is None
        assert widget.current_editor is None
        assert not widget.save()

    def test_open_files_in_tabs(self, widget, folder):
        widget.open_file(folder / "a.jsonl", line=2)
        widget.open_file(folder / "vars.yaml")
        widget.open_file(folder / "a.jsonl")
        assert [p.name for p in widget.open_files] == ["a.jsonl", "vars.yaml"]
        assert widget.current_file == (folder / "a.jsonl").resolve()
        assert widget.current_editor.cursor_line_column[0] == 2
        assert widget.editor_of(folder / "vars.yaml").language.value == "yaml"
        assert widget.editor_of(folder / "nope") is None

    def test_file_that_cannot_be_read(self, widget, folder):
        (folder / "bin.jsonl").write_bytes(b"\xff\xfe\x00")
        failures = []
        widget.openFailed.connect(lambda path, message: failures.append(path.name))
        widget.open_file(folder / "bin.jsonl")
        assert failures == ["bin.jsonl"]
        assert widget.open_files == []

    def test_new_file_opens_empty(self, widget, folder):
        widget.open_file(folder / "new.jsonl")
        assert widget.current_editor.toPlainText() == ""

    def test_preview_tab_is_replaced_by_the_next_one(self, widget, folder):
        widget.open_file(folder / "a.jsonl", preview=True)
        widget.open_file(folder / "b.jsonl", preview=True)
        assert [p.name for p in widget.open_files] == ["b.jsonl"]

    def test_edited_or_opened_for_real_tabs_stay(self, widget, folder):
        widget.open_file(folder / "a.jsonl", preview=True)
        _type(widget, " ")
        widget.open_file(folder / "b.jsonl", preview=True)
        widget.open_file(folder / "vars.yaml", preview=True)
        widget.open_file(folder / "vars.yaml")
        widget.open_file(folder / "b.jsonl", preview=True)
        assert [p.name for p in widget.open_files] == ["a.jsonl", "vars.yaml", "b.jsonl"]

    def test_state_changes_are_reported(self, widget, folder):
        events = []
        widget.stateChanged.connect(lambda: events.append(1))
        widget.open_file(folder / "a.jsonl")
        assert events
        events.clear()
        widget.close_tab(folder / "a.jsonl")
        assert events
        assert widget.close_tab(folder / "a.jsonl")


class TestSave(TestBase):
    def test_edit_and_save(self, widget, folder):
        saved = []
        widget.saved.connect(lambda path, text: saved.append((path.name, text)))
        widget.open_file(folder / "b.jsonl")
        widget.current_editor.set_text("changed")
        _type(widget, "!")
        assert widget.dirty_files() == [(folder / "b.jsonl").resolve()]
        assert widget._tabs.tabText(0) == "b.jsonl ●"

        assert widget.save()

        assert (folder / "b.jsonl").read_text() == "!changed"
        assert saved == [("b.jsonl", "!changed")]
        assert widget.dirty_files() == []
        assert widget._tabs.tabText(0) == "b.jsonl"

    def test_ctrl_s_saves(self, widget, folder):
        widget.open_file(folder / "b.jsonl")
        _type(widget, "x")
        QTest.keyClick(widget.current_editor, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
        assert (folder / "b.jsonl").read_text().startswith("x")

    def test_save_all(self, widget, folder):
        for name in ("a.jsonl", "b.jsonl"):
            widget.open_file(folder / name)
            _type(widget, "x")
        assert widget.save_all()
        assert (folder / "a.jsonl").read_text().startswith("x")
        assert (folder / "b.jsonl").read_text().startswith("x")

    def test_overwriting_a_changed_file_asks(self, widget, folder):
        widget.open_file(folder / "b.jsonl")
        _type(widget, "mine")
        (folder / "b.jsonl").write_text("theirs")
        asked = []
        widget.confirm_overwrite = lambda path: asked.append(path.name) or False

        assert not widget.save()
        assert asked == ["b.jsonl"]
        assert (folder / "b.jsonl").read_text() == "theirs"

        widget.confirm_overwrite = lambda path: True
        assert widget.save()
        assert (folder / "b.jsonl").read_text().startswith("mine")

    def test_save_error_is_reported(self, widget, folder, monkeypatch):
        widget.open_file(folder / "b.jsonl")
        _type(widget, "x")
        messages = []
        monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append(args[2]))
        monkeypatch.setattr(widget.buffer_of(folder / "b.jsonl"), "save", lambda: (_ for _ in ()).throw(OSError("disk full")))
        assert not widget.save()
        assert "disk full" in messages[0]

    def test_default_overwrite_question(self, widget, folder, monkeypatch):
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Save)
        assert widget._ask_overwrite(folder / "a.jsonl")
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
        assert not widget._ask_overwrite(folder / "a.jsonl")


class TestClose(TestBase):
    def _dirty(self, widget, folder):
        widget.open_file(folder / "b.jsonl")
        _type(widget, "x")

    @pytest.mark.parametrize(
        "answer, closed, saved",
        [
            (QMessageBox.StandardButton.Save, True, True),
            (QMessageBox.StandardButton.Discard, True, False),
            (QMessageBox.StandardButton.Cancel, False, False),
        ],
    )
    def test_closing_a_changed_tab_asks(self, widget, folder, monkeypatch, answer, closed, saved):
        self._dirty(widget, folder)
        monkeypatch.setattr(QMessageBox, "question", lambda *args: answer)
        assert widget.close_tab(folder / "b.jsonl") == closed
        assert (widget.open_files == []) == closed
        assert (folder / "b.jsonl").read_text().startswith("x") == saved

    def test_close_button_of_the_tab(self, widget, folder):
        widget.open_file(folder / "a.jsonl")
        widget._tabs.tabCloseRequested.emit(0)
        assert widget.open_files == []

    def test_close_all(self, widget, folder):
        widget.open_file(folder / "a.jsonl")
        widget.open_file(folder / "b.jsonl")
        assert widget.close_all()
        assert widget.open_files == []


class TestChangesOnDisk(TestBase):
    def test_tab_without_changes_follows_the_file(self, widget, folder):
        widget.open_file(folder / "b.jsonl")
        (folder / "b.jsonl").write_text('{"page": 3}\n')
        assert widget.external_changes({folder / "b.jsonl"}) == {(folder / "b.jsonl").resolve(): DiskChange.RELOADED}
        assert widget.current_editor.toPlainText() == '{"page": 3}\n'
        assert widget.external_changes({folder / "a.jsonl"}) == {}

    def test_tab_with_changes_shows_a_banner(self, widget, folder):
        widget.open_file(folder / "b.jsonl")
        _type(widget, "mine")
        (folder / "b.jsonl").write_text("theirs")
        widget.external_changes({folder / "b.jsonl"})
        page = widget._pages[(folder / "b.jsonl").resolve()]
        assert not page.banner.isHidden()
        assert widget.current_editor.toPlainText().startswith("mine")

        # WHEN: the user keeps their version
        page.banner.keepRequested.emit()

        # THEN
        assert page.banner.isHidden()
        assert widget.dirty_files()
        assert widget.save()
        assert (folder / "b.jsonl").read_text().startswith("mine")

    def test_reload_from_disk_drops_the_changes(self, widget, folder):
        widget.open_file(folder / "b.jsonl")
        _type(widget, "mine")
        (folder / "b.jsonl").write_text("theirs")
        widget.external_changes({folder / "b.jsonl"})
        page = widget._pages[(folder / "b.jsonl").resolve()]

        page.banner.reloadRequested.emit()

        assert widget.current_editor.toPlainText() == "theirs"
        assert page.banner.isHidden()
        assert widget.dirty_files() == []

    def test_deleted_file_closes_a_clean_tab(self, widget, folder):
        widget.open_file(folder / "b.jsonl")
        (folder / "b.jsonl").unlink()
        widget.external_changes({folder / "b.jsonl"})
        assert widget.open_files == []

    def test_deleted_file_with_changes_keeps_the_tab_and_says_so(self, widget, folder):
        widget.open_file(folder / "b.jsonl")
        _type(widget, "mine")
        (folder / "b.jsonl").unlink()
        widget.external_changes({folder / "b.jsonl"})
        page = widget._pages[(folder / "b.jsonl").resolve()]
        assert not page.banner.isHidden()
        assert "deleted" in page.banner.text
        widget.confirm_overwrite = lambda path: True
        assert widget.save()
        assert (folder / "b.jsonl").exists()

    def test_reload_and_keep_of_unknown_files_do_nothing(self, widget, folder):
        widget.reload(folder / "nope")
        widget.keep_mine(folder / "nope")


class TestMarkersAndOptions(TestBase):
    def test_markers_reach_open_and_later_opened_files(self, widget, folder):
        marker = SourceIssue(1, 0, 1, Severity.WARNING, "outside of the screen")
        widget.open_file(folder / "a.jsonl")
        widget.set_markers({(folder / "a.jsonl").resolve(): [marker], (folder / "b.jsonl").resolve(): [marker]})
        assert widget.current_editor._app_markers == [marker]
        widget.open_file(folder / "b.jsonl")
        assert widget.current_editor._app_markers == [marker]
        widget.set_markers({})
        assert widget.current_editor._app_markers == []

    def test_variables_for_the_completion(self, widget, folder):
        widget.set_variables(lambda path: [path.name + ".x"])
        widget.open_file(folder / "a.jsonl")
        assert widget.current_editor.completion._variables() == ["a.jsonl.x"]

    def test_options_apply_to_open_and_new_tabs(self, widget, folder):
        widget.open_file(folder / "a.jsonl")
        widget.set_word_wrap(True)
        widget.set_show_whitespace(True)
        widget.open_file(folder / "b.jsonl")
        for name in ("a.jsonl", "b.jsonl"):
            editor = widget.editor_of(folder / name)
            assert editor.lineWrapMode().name == "WidgetWidth"
        widget.refresh_theme()

    def test_find_bar_searches_the_current_tab(self, widget, folder):
        widget.open_file(folder / "a.jsonl")
        QTest.keyClick(widget.current_editor, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        assert widget.find_bar.isVisible()
        QTest.keyClicks(widget.find_bar._find, "id")
        assert len(widget.current_editor.extraSelections()) >= 3
        widget.find_bar._step(True)
        assert widget.current_editor.textCursor().selectedText() == "id"
        QTest.keyClick(widget.find_bar, Qt.Key.Key_Escape)
        assert not widget.find_bar.isVisible()
        assert len(widget.current_editor.extraSelections()) < 3

    def test_status_line(self, widget, folder):
        widget.open_file(folder / "a.jsonl", line=2, column=3)
        assert "Ln 2, Col 4" in widget._status.text()
        assert "JSONL" in widget._status.text()
        widget.current_editor.set_text("{")
        assert "problem" in widget._status.text()
        widget.close_all(ask=False)
        assert widget._status.text() == ""


class TestFindBar(TestBase):
    def test_replace(self, widget, folder):
        widget.open_file(folder / "a.jsonl")
        bar = widget.find_bar
        bar.open_bar()
        QTest.keyClicks(bar._find, "page")
        QTest.keyClicks(bar._replace, "side")
        bar._replace_all()
        assert widget.current_editor.toPlainText().count("side") == 2
        assert "Replaced 2" in bar._status.text()
        bar._replace_one()
        bar._step(False)
        bar._case.setChecked(True)
        bar._regex.setChecked(True)
        bar._find.setText("(")
        assert "Invalid" in bar._status.text()

    def test_search_without_an_editor(self, qapp, settings):
        from openhasp_config_manager.gui.qt.widgets.find_bar import FindBar

        bar = FindBar()
        bar.open_bar()
        bar._search()
        bar._step(True)
        bar._replace_one()
        bar._replace_all()
        bar.set_editor(None)
        assert not bar.isVisible()

    def test_selected_text_becomes_the_search(self, widget, folder):
        widget.open_file(folder / "a.jsonl")
        widget.current_editor.selectAll()
        widget.find_bar.open_bar()
        assert widget.find_bar._find.text() == ""  # more than one line: not used
        cursor = widget.current_editor.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(6, cursor.MoveMode.KeepAnchor)
        widget.current_editor.setTextCursor(cursor)
        widget.find_bar.open_bar()
        assert widget.find_bar._find.text() == "page"
        widget.find_bar.set_editor(None)


class TestCodeView(TestBase):
    def test_modes_show_the_views(self, widget):
        rendered = QWidget()
        view = CodeView(widget, rendered)
        view.show()
        assert view.mode == CodeViewMode.RENDERED
        assert not view.shows_source
        assert widget.isHidden() and not rendered.isHidden()

        view.show_source()
        assert view.mode == CodeViewMode.SPLIT
        assert view.shows_source
        assert not widget.isHidden() and not rendered.isHidden()

        view.set_mode(CodeViewMode.SOURCE)
        assert not widget.isHidden() and rendered.isHidden()
        view.show_source()
        assert view.mode == CodeViewMode.SOURCE
        view.close()

    def test_mode_and_layout_are_remembered(self, widget):
        view = CodeView(widget, QWidget())
        view.set_mode(CodeViewMode.SPLIT)
        view._toggle_orientation()
        view._wrap_action.setChecked(True)
        view._whitespace_action.setChecked(True)
        view.save_state()
        view.close()

        again = CodeView(widget, QWidget())
        assert again.mode == CodeViewMode.SPLIT
        assert again._splitter.orientation() == Qt.Orientation.Vertical
        assert again._wrap_action.isChecked() and again._whitespace_action.isChecked()
        again._toggle_orientation()
        assert again._splitter.orientation() == Qt.Orientation.Horizontal
        again._reset_zoom()
        again.close()

    def test_unknown_stored_mode_falls_back(self, widget):
        QSettings().setValue("code_view/mode", "nonsense")
        assert CodeView(widget, QWidget()).mode == CodeViewMode.RENDERED

    def test_zoom_reset_with_an_open_file(self, widget, folder):
        widget.open_file(folder / "a.jsonl")
        view = CodeView(widget, QWidget())
        widget.current_editor.zoom(3)
        view._reset_zoom()
        assert widget.current_editor.font().pointSize() == 10
        # the view owns the widget and is deleted when the test ends, before the fixture closes the tabs
        widget.setParent(None)


class TestEditorFeatures(TestBase):
    def test_rename_id_asks_for_the_new_id(self, widget, folder):
        widget.open_file(folder / "a.jsonl", line=1)
        asked = []
        widget.ask_new_id = lambda current: asked.append(current) or 5

        widget.current_editor.renameRequested.emit()

        assert asked == [1]
        assert widget.current_editor.toPlainText().startswith('{"page": 1, "id": 5}')
        assert widget.buffer_of(folder / "a.jsonl").is_dirty

    def test_rename_cancelled_or_not_possible(self, widget, folder):
        widget.open_file(folder / "a.jsonl", line=1)
        widget.ask_new_id = lambda current: None
        widget.current_editor.renameRequested.emit()
        assert not widget.dirty_files()

        widget.ask_new_id = lambda current: 2
        widget.current_editor.renameRequested.emit()
        assert "already used" in widget._status.text()
        assert not widget.dirty_files()

        widget.open_file(folder / "vars.yaml")
        widget.current_editor.renameRequested.emit()
        assert "plain number" in widget._status.text()

    def test_the_input_dialog(self, widget, monkeypatch):
        from PyQt6.QtWidgets import QInputDialog

        monkeypatch.setattr(QInputDialog, "getInt", lambda *args: (7, True))
        assert widget._ask_new_id(3) == 7
        monkeypatch.setattr(QInputDialog, "getInt", lambda *args: (7, False))
        assert widget._ask_new_id(3) is None

    def test_ctrl_click_opens_the_referenced_file(self, widget, folder):
        (folder / "devices").mkdir()
        (folder / "devices" / "boot.cmd").write_text("run L:/b.jsonl\nrun L:/nope.jsonl\n")
        widget.open_file(folder / "devices" / "boot.cmd")

        widget.current_editor.linkRequested.emit("b.jsonl")
        assert widget.current_file == (folder / "b.jsonl").resolve()

        widget.open_file(folder / "devices" / "boot.cmd")
        widget.current_editor.linkRequested.emit("nope.jsonl")
        assert "L:/nope.jsonl" in widget._status.text()
        assert widget.current_file == (folder / "devices" / "boot.cmd").resolve()

    def test_hidden_folders_are_not_searched_for_links(self, widget, folder):
        (folder / ".hidden").mkdir()
        (folder / ".hidden" / "x.jsonl").write_text("{}\n")
        widget.open_file(folder / "a.jsonl")
        widget.current_editor.linkRequested.emit("x.jsonl")
        assert widget.current_file == (folder / "a.jsonl").resolve()

    def test_the_object_at_the_cursor_is_reported_when_the_user_moves(self, widget, folder):
        widget.open_file(folder / "a.jsonl")
        found = []
        widget.objectAtCursorChanged.connect(lambda path, index: found.append((path.name, index)))
        editor = widget.current_editor

        # moved by the app: no signal
        editor.clearFocus()
        editor.go_to(2, 0)
        assert found == []

        # moved by the user
        widget.activateWindow()
        editor.setFocus()
        QTest.qWait(50)
        if not editor.hasFocus():  # offscreen windows may not take the focus
            pytest.skip("no focus in this environment")
        editor.go_to(1, 0)
        assert found == [("a.jsonl", 0)]
