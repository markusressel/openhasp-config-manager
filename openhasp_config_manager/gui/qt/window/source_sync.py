from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt6 import QtCore

from openhasp_config_manager.gui.domain.gui_state import relative
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.domain.problems import Severity
from openhasp_config_manager.gui.domain.source.issues import SourceIssue
from openhasp_config_manager.gui.domain.variables.definitions import Definition, VariableDefinitions
from openhasp_config_manager.gui.domain.variables.usages import Usage, VariableUsages
from openhasp_config_manager.gui.qt.ui_session_store import UiSessionStore
from openhasp_config_manager.gui.qt.widgets.source.code_view import CodeView
from openhasp_config_manager.gui.qt.widgets.source.rendered_view import FileRenderedView
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_layout_editor import PageLayoutEditorWidget
from openhasp_config_manager.gui.qt.widgets.source.source_editor import SourceEditorWidget


class SourceEditorSync(QtCore.QObject):
    """
    Keeps the text editor and the draft of the page layout editor in step: selecting an object in the preview shows where it
    is written, moving the cursor into an object selects it, the problems of the page are marked in their files, and the open
    tabs are remembered for the next start. Saving a tab is up to the window (it reloads the draft). The rendered view of the code
    view (`file_view`) shows the objects of the file in the current tab.
    """

    def __init__(
        self,
        source_editor: SourceEditorWidget,
        code_view: CodeView,
        page_editor: PageLayoutEditorWidget,
        session: Callable[[], Optional[PlateSession]],
        ui_session: UiSessionStore,
        config_dir: Path,
        file_view: FileRenderedView,
        parent: Optional[QtCore.QObject] = None,
    ):
        """:param session: the draft of the selected device, None if there is none"""
        super().__init__(parent)
        self._source_editor = source_editor
        self._code_view = code_view
        self._page_editor = page_editor
        self._session = session
        self._ui_session = ui_session
        self._config_dir = config_dir
        self._file_view = file_view
        self._definitions = VariableDefinitions(config_dir)
        self._variable_usages: Optional[VariableUsages] = None
        self._restoring_open_files = False

        page_editor.stateChanged.connect(self.update_markers)
        page_editor.stateChanged.connect(self.update_file_view)
        page_editor.page_preview_widget.selectionChanged.connect(self._select_in_file_view)
        page_editor.page_preview_widget.selectionChanged.connect(self._reveal_selection)
        source_editor.objectAtCursorChanged.connect(self._select_object_of_cursor)
        page_editor.openSourceRequested.connect(self.open_source)
        source_editor.stateChanged.connect(self._remember_open_files)
        source_editor.stateChanged.connect(self.update_file_view)
        source_editor.set_variables(self.variables_of_file)
        source_editor.set_definition_finder(self.find_definition)
        source_editor.set_usages_finder(self.find_usages)
        source_editor.set_value_source(self.variable_value, self.render_text)
        page_editor.stateChanged.connect(source_editor.refresh_values)

    def open_file(self, path: Path):
        """Show a file in the text editor, for editing (not as a preview)."""
        self._code_view.show_source()
        self._source_editor.open_file(path)

    def open_source(self, path: Path, line: int):
        """Show a file in the text editor at a line, e.g. the part of an included object."""
        self._code_view.show_source()
        self._source_editor.open_file(path, line)

    def variables_of_file(self, path: Path) -> List[str]:
        """:return: the template variables a file of the draft can use, for the completion"""
        session = self._loaded_session()
        component = None if session is None else session.component_at(path)
        return [] if component is None else session.variable_names(component.key)

    def variable_value(self, path: Path, name: str) -> Any:
        """
        :return: the value of the template variable `name` in a file of the device (see `PlateSession.variable_value_at`)
        :raises KeyError: if it has none
        """
        session = self._loaded_session()
        if session is None:
            raise KeyError(name)
        return session.variable_value_at(path, name)

    def render_text(self, path: Path, text: str) -> Optional[str]:
        """:return: what a text with templates renders to in a file of the device, None if no device is loaded"""
        session = self._loaded_session()
        return None if session is None else session.render_text_at(path, text)

    def find_definition(self, path: Path, name: str) -> Optional[Definition]:
        """:return: where the variable `name`, used in a file, is defined"""
        session = self._session()
        device_path = None if session is None else session.device.path
        return self._definitions.find(name, path, device_path)

    def set_variable_usages(self, usages: VariableUsages):
        """Where the variables are used, by all devices (see `LoadedDevice.variable_usages`)."""
        self._variable_usages = usages

    def find_usages(self, path: Path, name: str) -> List[Usage]:
        """:return: where the variable `name`, defined in a file, is used"""
        return [] if self._variable_usages is None else self._variable_usages.usages(path, name)

    # --- open tabs ---

    def restore_open_files(self):
        """Open the files of the last session that still exist."""
        session = self._ui_session.session
        self._restoring_open_files = True
        try:
            for name in session.open_files:
                path = self._config_dir / name
                if path.is_file():
                    self._source_editor.open_file(path, focus=False)
            current = None if session.current_file is None else self._config_dir / session.current_file
            if current is not None and current.is_file():
                self._source_editor.open_file(current, focus=False)
        finally:
            self._restoring_open_files = False
        self._remember_open_files()

    def _remember_open_files(self):
        if self._restoring_open_files:
            return
        current = self._source_editor.current_file
        session = self._ui_session.session
        session.open_files = [relative(path, self._config_dir) for path in self._source_editor.open_files]
        session.current_file = None if current is None else relative(current, self._config_dir)
        self._ui_session.save()

    # --- objects ---

    def _loaded_session(self) -> Optional[PlateSession]:
        session = self._session()
        return session if session is not None and session.is_loaded else None

    def _shown_session(self) -> Optional[PlateSession]:
        """:return: the draft the page editor shows, None while it shows none or another one (loading)"""
        session = self._loaded_session()
        return session if session is not None and self._page_editor.session is session else None

    def _reveal_selection(self, selected: list):
        """Selecting an object in the preview shows where it is written, if the source is visible."""
        session = self._session()
        if len(selected) != 1 or not self._code_view.shows_source or session is None or session.is_dirty:
            return
        obj = selected[0].obj_data
        line = session.line_of(obj)
        if line is None or self._cursor_is_in_object(session, obj):
            return
        component = session.component_of(obj)
        self._source_editor.open_file(component.path, line, focus=False, preview=True)
        self._flash_object(session, obj)

    def _flash_object(self, session: PlateSession, obj: Dict):
        """Highlight the lines of an object in its tab for a moment, if the text is the one the draft was loaded from."""
        component = session.component_of(obj)
        editor = self._source_editor.editor_of(component.path)
        buffer = self._source_editor.buffer_of(component.path)
        if editor is None or buffer is None or buffer.text != component.content:
            return
        index = session.source_index(obj)
        found = next((source for source in editor.objects() if source.index == index), None)
        if found is not None:
            editor.flash_lines(found.start_line, found.end_line)

    def _cursor_is_in_object(self, session: PlateSession, obj: Dict) -> bool:
        """Whether the cursor of the text editor is already in the lines of an object (so it doesn't jump to its first line)."""
        editor = self._source_editor.editor_of(session.component_of(obj).path)
        current = None if editor is None else editor.object_at_cursor()
        return current is not None and current.index == session.source_index(obj)

    def _select_object_of_cursor(self, path: Path, index: int):
        """The cursor of the text editor is in an object: select it in the preview, on its page."""
        session = self._shown_session()
        if index < 0 or session is None:
            return
        component = session.component_at(path)
        buffer = self._source_editor.buffer_of(path)
        # the text must be the one the objects of the draft come from, or the indices are not the same
        if component is None or buffer is None or buffer.text != component.content:
            return
        obj = session.object_of_source(component.key, index)
        if obj is None:
            return
        page = obj.get("page")
        if isinstance(page, int) and page > 0 and page != self._page_editor.current_index:
            self._page_editor.set_page_index(page)
        self._page_editor.page_preview_widget.select_object(obj)

    def update_file_view(self):
        """The rendered view shows the objects of the file in the current tab, as the draft rendered them from the saved file."""
        session = self._shown_session()
        path = self._source_editor.current_file
        view = self._file_view.view
        objects = []
        out_of_date = False
        if path is None:
            view.setPlaceholderText("Open a file to see it rendered.")
        else:
            found = None if session is None else session.objects_of_file(path)
            objects = found or []
            view.setPlaceholderText("No objects of this file in the draft." if found is None else "No objects in this file.")
            component = None if session is None else session.component_at(path)
            buffer = self._source_editor.buffer_of(path)
            out_of_date = component is not None and buffer is not None and buffer.text != component.content
        self._file_view.set_out_of_date(out_of_date)
        view.set_objects(objects)
        self._select_in_file_view(self._page_editor.page_preview_widget.selected_items(), scroll=False)

    def _select_in_file_view(self, selected: list, scroll: bool = True):
        self._file_view.view.set_selected_objects([widget.obj_data for widget in selected], scroll=scroll)

    def update_markers(self):
        """
        The problems of the open page are shown in the editors of their files, and what is wrong with the directives of the files
        of the draft (`!include`) where it is: at a directive, or in a part.
        """
        session = self._shown_session()
        markers: Dict[Path, List[SourceIssue]] = {}
        for problem in [] if session is None else self._page_editor.problems:
            line = session.line_of(problem.obj)
            if line is not None:
                path = session.component_of(problem.obj).path.resolve()
                markers.setdefault(path, []).append(SourceIssue(line, 0, 1, problem.severity, problem.message))
        for errors in [] if session is None else session.include_errors().values():
            for error in errors:
                issue = SourceIssue(error.line, 0, 1, Severity.ERROR, error.describe(self._config_dir))
                markers.setdefault(error.file.resolve(), []).append(issue)
        self._source_editor.set_markers(markers)
