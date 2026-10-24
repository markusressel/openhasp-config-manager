import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QMessageBox, QStackedLayout, QTabWidget, QVBoxLayout, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.source_buffers import DiskChange, SourceBuffer, SourceBuffers, read_text
from openhasp_config_manager.gui.domain.source_syntax import language_of
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.widgets.code_editor import CodeEditor, Marker
from openhasp_config_manager.gui.qt.widgets.find_bar import FindBar

LOGGER = logging.getLogger(__name__)


class _ConflictBanner(QFrame):
    """The file of a tab with changes changed on disk too: the user chooses which version to keep."""

    reloadRequested = QtCore.pyqtSignal()
    keepRequested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "banner")
        row = UiComponents.create_row(parent=self, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.setContentsMargins(UiDimensions.one, UiDimensions.half, UiDimensions.one, UiDimensions.half)
        row.addWidget(UiComponents.create_icon_label("file-alert-outline"))
        self._text = UiComponents.create_label("", word_wrap=True)
        row.addWidget(self._text, 1)
        row.addWidget(
            UiComponents.create_button(
                "Reload from disk",
                self.reloadRequested.emit,
                icon="refresh",
                tooltip="Discard the changes in this editor and load the file as it is on disk now",
            )
        )
        row.addWidget(
            UiComponents.create_button(
                "Keep my version",
                self.keepRequested.emit,
                icon="close",
                tooltip="Keep the text in this editor. Saving overwrites the file on disk.",
            )
        )
        self.hide()

    def show_conflict(self, deleted: bool):
        self._text.setText(
            "This file was deleted on disk. Saving writes it again."
            if deleted
            else "This file changed on disk, and you have unsaved changes here."
        )
        self.show()


class _Page(QWidget):
    """One tab: the banner above the editor."""

    def __init__(self, editor: CodeEditor):
        super().__init__()
        self.editor = editor
        self.banner = _ConflictBanner()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.banner)
        layout.addWidget(editor, 1)


class SourceEditorWidget(QWidget):
    """
    The text editor for the files of the config directory, one tab per open file. The files follow changes on disk
    (`external_changes`): a tab without changes reloads quietly, a tab with changes asks. Saving (Ctrl+S) writes the file and
    reports it (`saved`), the window then reloads the pages.
    """

    # a file was written: its path and the text
    saved = QtCore.pyqtSignal(object, str)
    # the open files, the current tab or the dirty state changed
    stateChanged = QtCore.pyqtSignal()
    openFailed = QtCore.pyqtSignal(object, str)

    def __init__(self, config_dir: Path, parent=None):
        super().__init__(parent)
        self._config_dir = config_dir
        self._buffers = SourceBuffers()
        self._pages: Dict[Path, _Page] = {}
        # the file opened by selecting an object: replaced by the next one until the user edits it or opens it for real
        self._preview_tab: Optional[Path] = None
        self._variables: Callable[[Path], List[str]] = lambda path: []
        self._markers: Dict[Path, List[Marker]] = {}
        self._word_wrap = False
        self._show_whitespace = False
        # asks whether to overwrite a file that changed on disk; replaced in tests
        self.confirm_overwrite: Callable[[Path], bool] = self._ask_overwrite

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.tabCloseRequested.connect(lambda index: self.close_tab(self._path_at(index)))
        self._tabs.currentChanged.connect(self._on_current_changed)

        self._placeholder = UiComponents.create_label(
            "Double-click a file in the Files tree to edit it here.\nChanges made outside of the app show up automatically.",
            role="hint",
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.find_bar = FindBar()
        self._status = UiComponents.create_label("", role="hint")
        self._status.setContentsMargins(UiDimensions.one, 0, UiDimensions.one, 0)

        body = QWidget()
        stack = QStackedLayout(body)
        stack.addWidget(self._placeholder)
        stack.addWidget(self._tabs)
        self._stack = stack

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.find_bar)
        layout.addWidget(body, 1)
        layout.addWidget(self._status)
        self._update_visibility()

    # --- files ---

    @property
    def open_files(self) -> List[Path]:
        return [self._path_at(index) for index in range(self._tabs.count())]

    @property
    def current_file(self) -> Optional[Path]:
        return self._path_at(self._tabs.currentIndex()) if self._tabs.count() else None

    @property
    def current_editor(self) -> Optional[CodeEditor]:
        page = self._tabs.currentWidget()
        return None if page is None else page.editor

    def editor_of(self, path: Path) -> Optional[CodeEditor]:
        page = self._pages.get(path.resolve())
        return None if page is None else page.editor

    def buffer_of(self, path: Path) -> Optional[SourceBuffer]:
        return self._buffers.get(path)

    def dirty_files(self) -> List[Path]:
        return [buffer.path for buffer in self._buffers.dirty()]

    def set_variables(self, provider: Callable[[Path], List[str]]):
        """The template variables a file can use, for the completion."""
        self._variables = provider

    def open_file(self, path: Path, line: Optional[int] = None, column: int = 0, focus: bool = True, preview: bool = False):
        """
        Show a file in its tab (a new one if it is not open), at a line.
        :param preview: a tab that the next preview replaces, unless it was edited
        """
        path = path.resolve()
        if path not in self._pages:
            try:
                buffer = self._buffers.open(path)
            except (OSError, UnicodeDecodeError) as ex:
                LOGGER.warning(f"Can't open {path}: {ex}")
                self.openFailed.emit(path, str(ex))
                return
            self._add_page(buffer, replace_preview=preview)
            self._preview_tab = path if preview else self._preview_tab
        elif not preview and self._preview_tab == path:
            self._preview_tab = None
        self._tabs.setCurrentWidget(self._pages[path])
        editor = self._pages[path].editor
        if line is not None:
            editor.go_to(line, column)
        if focus:
            editor.setFocus()
        self.stateChanged.emit()

    def _add_page(self, buffer: SourceBuffer, replace_preview: bool):
        if replace_preview and self._preview_tab in self._pages and self._preview_tab not in self.dirty_files():
            self._remove_tab(self._preview_tab)
        editor = CodeEditor(language_of(buffer.path))
        editor.set_text(buffer.text)
        editor.set_variables(lambda path=buffer.path: self._variables(path))
        editor.set_app_markers(self._markers.get(buffer.path, []))
        editor.set_word_wrap(self._word_wrap)
        editor.set_show_whitespace(self._show_whitespace)
        page = _Page(editor)
        path = buffer.path
        editor.textEdited.connect(lambda path=path: self._on_edited(path))
        editor.saveRequested.connect(lambda path=path: self.save(path))
        editor.findRequested.connect(self.find_bar.open_bar)
        editor.issuesChanged.connect(self._update_status)
        editor.cursorPositionChanged.connect(self._update_status)
        page.banner.reloadRequested.connect(lambda path=path: self.reload(path))
        page.banner.keepRequested.connect(lambda path=path: self.keep_mine(path))
        self._pages[path] = page
        self._tabs.addTab(page, buffer.path.name)
        self._tabs.setTabToolTip(self._tabs.indexOf(page), self._relative(path))
        self._update_visibility()
        self._update_tab(path)

    def close_tab(self, path: Path, ask: bool = True) -> bool:
        """:return: whether the tab was closed (not if the user cancels)"""
        path = path.resolve()
        buffer = self._buffers.get(path)
        if buffer is None:
            return True
        if ask and buffer.is_dirty and not self._confirm_discard(buffer):
            return False
        self._remove_tab(path)
        return True

    def close_all(self, ask: bool = True) -> bool:
        return all(self.close_tab(path, ask) for path in self.open_files)

    def _remove_tab(self, path: Path):
        page = self._pages.pop(path, None)
        if page is not None:
            self._tabs.removeTab(self._tabs.indexOf(page))
            page.deleteLater()
        self._buffers.close(path)
        if self._preview_tab == path:
            self._preview_tab = None
        self._update_visibility()
        self.stateChanged.emit()

    def _confirm_discard(self, buffer: SourceBuffer) -> bool:
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            f"{buffer.path.name} has changes that are not saved.",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save(buffer.path)
        return answer == QMessageBox.StandardButton.Discard

    # --- saving ---

    def save(self, path: Optional[Path] = None) -> bool:
        """
        Write a file (the current one by default). Asks first if it changed on disk since the editor read it.
        :return: whether the file was written
        """
        path = path or self.current_file
        buffer = None if path is None else self._buffers.get(path)
        if buffer is None:
            return False
        if buffer.conflict or read_text(buffer.path) != buffer.disk_text:
            if not self.confirm_overwrite(buffer.path):
                return False
        try:
            text = buffer.save()
        except OSError as ex:
            QMessageBox.critical(self, "Save failed", f"{buffer.path}: {ex}")
            return False
        self._pages[buffer.path].banner.hide()
        self._update_tab(buffer.path)
        self.saved.emit(buffer.path, text)
        self.stateChanged.emit()
        return True

    def save_all(self) -> bool:
        return all(self.save(buffer.path) for buffer in self._buffers.dirty())

    def _ask_overwrite(self, path: Path) -> bool:
        answer = QMessageBox.question(
            self,
            "Overwrite file?",
            f"{path.name} changed on disk since it was opened here. Saving overwrites those changes.",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Save

    # --- changes on disk ---

    def external_changes(self, paths: Set[Path]) -> Dict[Path, DiskChange]:
        """Files changed outside of the editor: open tabs without changes follow, those with changes show a banner."""
        result = self._buffers.on_disk_changed(paths)
        for path, change in result.items():
            page = self._pages[path]
            if change == DiskChange.RELOADED:
                page.editor.set_text(self._buffers.get(path).text)
            elif change == DiskChange.CONFLICT:
                page.banner.show_conflict(deleted=read_text(path) is None)
            elif change == DiskChange.DELETED:
                self._remove_tab(path)
                continue
            self._update_tab(path)
        if any(change != DiskChange.NONE for change in result.values()):
            self.stateChanged.emit()
        return result

    def reload(self, path: Path):
        buffer = self._buffers.get(path)
        if buffer is not None:
            buffer.reload()
            self._pages[buffer.path].editor.set_text(buffer.text)
            self._pages[buffer.path].banner.hide()
            self._update_tab(buffer.path)
            self.stateChanged.emit()

    def keep_mine(self, path: Path):
        buffer = self._buffers.get(path)
        if buffer is not None:
            buffer.keep_mine()
            self._pages[buffer.path].banner.hide()
            self.stateChanged.emit()

    # --- markers ---

    def set_markers(self, markers: Dict[Path, List[Marker]]):
        """The problems the app found, per file (resolved paths), shown in the editors of those files."""
        self._markers = markers
        for path, page in self._pages.items():
            page.editor.set_app_markers(markers.get(path, []))

    # --- appearance ---

    def refresh_theme(self):
        for page in self._pages.values():
            page.editor.refresh_theme()

    def set_word_wrap(self, wrap: bool):
        self._word_wrap = wrap
        for page in self._pages.values():
            page.editor.set_word_wrap(wrap)

    def set_show_whitespace(self, show: bool):
        self._show_whitespace = show
        for page in self._pages.values():
            page.editor.set_show_whitespace(show)

    # --- internals ---

    def _path_at(self, index: int) -> Path:
        page = self._tabs.widget(index)
        return next(path for path, candidate in self._pages.items() if candidate is page)

    def _relative(self, path: Path) -> str:
        try:
            return path.relative_to(self._config_dir.resolve()).as_posix()
        except ValueError:
            return str(path)

    def _on_edited(self, path: Path):
        if self._preview_tab == path:
            self._preview_tab = None
        buffer = self._buffers.get(path)
        buffer.set_text(self._pages[path].editor.toPlainText())
        self._update_tab(path)
        self.stateChanged.emit()

    def _update_tab(self, path: Path):
        buffer = self._buffers.get(path)
        index = self._tabs.indexOf(self._pages[path])
        self._tabs.setTabText(index, buffer.path.name + (" ●" if buffer.is_dirty else ""))
        self._update_status()

    def _on_current_changed(self, _index: int):
        self.find_bar.set_editor(self.current_editor)
        self._update_status()
        self.stateChanged.emit()

    def _update_visibility(self):
        self._stack.setCurrentWidget(self._tabs if self._tabs.count() else self._placeholder)

    def _update_status(self):
        editor = self.current_editor
        if editor is None:
            self._status.setText("")
            return
        line, column = editor.cursor_line_column
        issues = len(editor.issues)
        self._status.setText(
            f"Ln {line}, Col {column}  ·  {editor.language.value.upper()}" + (f"  ·  {issues} problem(s)" if issues else "")
        )
