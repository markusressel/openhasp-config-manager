import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from PyQt6 import QtCore
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QStackedLayout, QTabWidget, QVBoxLayout, QWidget

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.source_buffers import DiskChange, SourceBuffer, SourceBuffers, read_text
from openhasp_config_manager.gui.domain.source_issues import SourceIssue
from openhasp_config_manager.gui.domain.source_links import link_targets, resolve_link
from openhasp_config_manager.gui.domain.source_syntax import language_of
from openhasp_config_manager.gui.domain.unused_variables import UnusedVariables
from openhasp_config_manager.gui.domain.navigation_history import Location, NavigationHistory
from openhasp_config_manager.gui.domain.variable_definitions import Definition
from openhasp_config_manager.gui.domain.variable_usages import Usage
from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.widgets.code_editor import CodeEditor
from openhasp_config_manager.gui.qt.widgets.find_bar import FindBar
from openhasp_config_manager.gui.qt.widgets.message_panel import DiskConflictBanner
from openhasp_config_manager.gui.qt.widgets.usages_menu import show_usages_menu

LOGGER = logging.getLogger(__name__)


class _Page(QWidget):
    """One tab: the banner above the editor."""

    def __init__(self, editor: CodeEditor):
        super().__init__()
        self.editor = editor
        self.banner = DiskConflictBanner(
            reload_tooltip="Discard the changes in this editor and load the file as it is on disk now",
            keep_title="Keep my version",
            keep_tooltip="Keep the text in this editor. Saving overwrites the file on disk.",
        )
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
    # the user moved the cursor into another object of a file: the path and the index of the object (-1: none)
    objectAtCursorChanged = QtCore.pyqtSignal(object, int)

    def __init__(self, config_dir: Path, parent=None):
        super().__init__(parent)
        self._config_dir = config_dir
        self._buffers = SourceBuffers()
        self._pages: Dict[Path, _Page] = {}
        # the file opened by selecting an object: replaced by the next one until the user edits it or opens it for real
        self._preview_tab: Optional[Path] = None
        self._variables: Callable[[Path], List[str]] = lambda path: []
        self._definitions: Callable[[Path, str], Optional[Definition]] = lambda path, name: None
        self._usages: Callable[[Path, str], List[Usage]] = lambda path, name: []
        self._history = NavigationHistory()
        # resolved path -> the hints and the text they were found in
        self._hints: Dict[Path, UnusedVariables] = {}
        self._markers: Dict[Path, List[SourceIssue]] = {}
        self._word_wrap = False
        self._show_whitespace = False
        # asks whether to overwrite a file that changed on disk; replaced in tests
        self.confirm_overwrite: Callable[[Path], bool] = self._ask_overwrite
        # asks for the new id of an object (None: cancelled); replaced in tests
        self.ask_new_id: Callable[[int], Optional[int]] = self._ask_new_id

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

    def set_definition_finder(self, finder: Callable[[Path, str], Optional[Definition]]):
        """Where a variable used in a file is defined, for Ctrl+click on the variables of templates."""
        self._definitions = finder

    def set_usages_finder(self, finder: Callable[[Path, str], List[Usage]]):
        """Where a variable defined in a YAML file is used, for Ctrl+click on its key."""
        self._usages = finder

    def open_file(
        self,
        path: Path,
        line: Optional[int] = None,
        column: int = 0,
        focus: bool = True,
        preview: bool = False,
        history: bool = True,
    ):
        """
        Show a file in its tab (a new one if it is not open), at a line.
        :param preview: a tab that the next preview replaces, unless it was edited
        :param history: whether going back leads to the place the cursor was at, unless this is a preview or does not focus
        """
        path = path.resolve()
        if history and focus and not preview:
            self._record_jump(path, line)
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

    @property
    def location(self) -> Optional[Location]:
        """:return: where the cursor is"""
        editor = self.current_editor
        return None if editor is None else Location(self.current_file, *editor.cursor_line_column)

    def go_back(self):
        """The "back" button of the mouse: return to the place the last jump came from."""
        self._go(self._history.back)

    def go_forward(self):
        self._go(self._history.forward)

    def _go(self, step: Callable):
        current = self.location
        if current is None:
            return
        target = step(current, lambda location: location.path.is_file())
        if target is not None:
            self.open_file(target.path, target.line, target.column - 1, history=False)

    def _record_jump(self, path: Path, line: Optional[int]):
        """A jump to a file (at a line) leaves the place the cursor is at, unless that is the target."""
        origin = self.location
        if origin is not None and (origin.path != path or (line is not None and origin.line != line)):
            self._history.jumped(origin)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.BackButton:
            self.go_back()
        elif event.button() == Qt.MouseButton.ForwardButton:
            self.go_forward()
        else:
            super().mousePressEvent(event)

    def _add_page(self, buffer: SourceBuffer, replace_preview: bool):
        if replace_preview and self._preview_tab in self._pages and self._preview_tab not in self.dirty_files():
            self._remove_tab(self._preview_tab)
        editor = CodeEditor(language_of(buffer.path))
        editor.set_text(buffer.text)
        editor.set_variables(lambda path=buffer.path: self._variables(path))
        editor.set_definition_finder(lambda name, path=buffer.path: self._definitions(path, name))
        editor.set_app_markers(self._markers.get(buffer.path, []))
        editor.set_word_wrap(self._word_wrap)
        editor.set_show_whitespace(self._show_whitespace)
        page = _Page(editor)
        path = buffer.path
        editor.textEdited.connect(lambda path=path: self._on_edited(path))
        editor.saveRequested.connect(lambda path=path: self.save(path))
        editor.findRequested.connect(self.find_bar.open_bar)
        editor.issuesChanged.connect(self._update_status)
        editor.renameRequested.connect(lambda path=path: self._rename_id(path))
        editor.linkRequested.connect(lambda target, path=path: self._open_link(path, target))
        editor.definitionRequested.connect(lambda name, path=path: self._open_definition(path, name))
        editor.backRequested.connect(self.go_back)
        editor.forwardRequested.connect(self.go_forward)
        editor.usagesRequested.connect(lambda name, position, path=path: self._show_usages(path, name, position))
        editor.cursorObjectChanged.connect(lambda index, path=path: self._on_object_at_cursor(path, index))
        editor.cursorPositionChanged.connect(self._update_status)
        page.banner.reloadRequested.connect(lambda path=path: self.reload(path))
        page.banner.keepRequested.connect(lambda path=path: self.keep_mine(path))
        self._pages[path] = page
        self._apply_hints(path)
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
            # the editor lives until the event loop deletes it, but its tab is gone
            page.editor.blockSignals(True)
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
                page.banner.show_message(
                    "This file was deleted on disk. Saving writes it again."
                    if read_text(path) is None
                    else "This file changed on disk, and you have unsaved changes here."
                )
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
            self._apply_hints(buffer.path)
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

    def set_markers(self, markers: Dict[Path, List[SourceIssue]]):
        """The problems the app found, per file (resolved paths), shown in the editors of those files."""
        self._markers = markers
        for path, page in self._pages.items():
            page.editor.set_app_markers(markers.get(path, []))

    def set_hints(self, hints: Dict[Path, UnusedVariables]):
        """
        Things worth knowing about the lines of files (resolved paths), e.g. unused variables. They are only shown while the text of
        the editor is the text they were found in: their lines are not right for any other.
        """
        self._hints = hints
        for path in self._pages:
            self._apply_hints(path)

    def _apply_hints(self, path: Path):
        hints = self._hints.get(path)
        buffer = self._buffers.get(path)
        shown = hints is not None and buffer is not None and buffer.text == hints.content
        self._pages[path].editor.set_hints(hints.issues if shown else [])

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

    def show_message(self, text: str):
        """Say something in the status line (until the cursor moves)."""
        self._status.setText(text)

    def _rename_id(self, path: Path):
        editor = self._pages[path].editor
        current = editor.object_id
        if current is None:
            self.show_message("Put the cursor in an object with a plain number as id to rename it.")
            return
        new_id = self.ask_new_id(current)
        if new_id is None or new_id == current:
            return
        error = editor.rename_id(new_id)
        self.show_message(error or f"Renamed id {current} to {new_id}")

    def _ask_new_id(self, current: int) -> Optional[int]:
        value, accepted = QInputDialog.getInt(
            self, "Rename id", "New id of the object (and the parentid of its children):", current, 0, 254
        )
        return value if accepted else None

    def _open_link(self, path: Path, target: str):
        """Ctrl+click on `L:/pages.jsonl`: open the file with that name on the plate."""
        config_dir = self._config_dir.resolve()
        found = resolve_link(target, link_targets(config_dir), config_dir, path)
        if found is None:
            self.show_message(f"No file in the config directory is L:/{target} on the plate")
            return
        self.open_file(found)

    def _open_definition(self, path: Path, name: str):
        """Ctrl+click on a variable of a template: open the file that defines it, at its line."""
        found = self._definitions(path, name)
        if found is None:
            self.show_message(f"The definition of {name} was not found")
            return
        self.open_file(found.path, found.line, found.column)

    def _show_usages(self, path: Path, name: str, position: QPoint):
        """Ctrl+click on the key of a variable: open where it is used, or let the user choose if that is more than one place."""
        usages = self._usages(path, name)
        if not usages:
            self.show_message(f"{name} is not used")
        elif len(usages) == 1:
            self._open_usage(usages[0])
        else:
            self._usages_menu = show_usages_menu(self, usages, self._config_dir, position, self._open_usage)

    def _open_usage(self, usage: Usage):
        self.open_file(usage.path, usage.line, usage.column)

    def _on_object_at_cursor(self, path: Path, index: int):
        # only when the user moved the cursor, not when the app showed a line
        if path == self.current_file and self._pages[path].editor.hasFocus():
            self.objectAtCursorChanged.emit(path, index)

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
        self._apply_hints(path)
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
