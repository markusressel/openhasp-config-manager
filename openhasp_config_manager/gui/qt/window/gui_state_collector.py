import os
import shlex
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List

from openhasp_config_manager.gui.domain.gui_state import (
    SCHEMA_VERSION,
    EditorTab,
    describe_connection,
    describe_draft,
    describe_editor,
    describe_files,
    describe_object,
    describe_part_mode,
    describe_problems,
    now,
    relative,
)
from openhasp_config_manager.gui.domain.draft.page_objects import get_navigable_page_indices


def collect_gui_state(window, running: bool = True) -> Dict[str, Any]:
    """The state for the state file (see `GuiStateFile`), as the GUI of a `MainWindow` is now."""
    editor = window.page_layout_editor_widget
    root = window.cfg_root
    session = window.session
    device = None
    problems: List[Dict[str, Any]] = []
    if session is not None and editor.session is session and session.is_loaded:
        screen = window.device.config.openhasp_config_manager.device.screen
        device = {
            "name": window.device.name,
            "folder": relative(window.device.path, root),
            "cmd": window.session_key[1],
            "screen": {"width": screen.width, "height": screen.height},
            "files": describe_files(session.components, session.working_objects, root),
            "page": editor.current_index,
            "pages": get_navigable_page_indices(session.working_objects),
            "edit_mode": editor.action_edit_mode.isChecked(),
            "live_preview": editor.plate.live,
            "selection": [
                describe_object(session, item.obj_data, root) for item in editor.page_preview_widget.selected_items()
            ],
            "new_objects_file": None
            if editor.target_component is None
            else relative(
                Path(editor.target_component)
                if session.part_mode is not None
                else next(c.path for c in session.components if c.key == editor.target_component),
                root,
            ),
            "part_mode": describe_part_mode(session, root),
            "draft": describe_draft(session, root),
        }
        problems = describe_problems(session, editor.problems, root, window.devices)
    return {
        "schema": SCHEMA_VERSION,
        "app": "openhasp-config-manager",
        "version": metadata.version("openhasp-config-manager"),
        "running": running,
        "pid": os.getpid(),
        "updated": now(),
        "config_dir": str(root),
        "check_command": f"openhasp-config-manager check -c {shlex.quote(str(root))} --json",
        "devices": [device.name for device in window.devices],
        "device": device,
        "editor": describe_editor(window.code_view.mode.value, _editor_tabs(window), window.source_editor.current_file, root),
        "problems": problems,
        "load_error": window.load_error,
        "files_changed_on_disk": [] if window.disk_changes_banner.isHidden() else window.disk_changes,
        "connection": describe_connection(window.connection.status),
        "last_operation": window.last_operation,
    }


def _editor_tabs(window) -> List[EditorTab]:
    tabs = []
    for path in window.source_editor.open_files:
        buffer = window.source_editor.buffer_of(path)
        line, column = window.source_editor.editor_of(path).cursor_line_column
        tabs.append(EditorTab(path, buffer.is_dirty, buffer.conflict, line, column))
    return tabs
