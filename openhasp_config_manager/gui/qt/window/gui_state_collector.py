import os
import shlex
from importlib import metadata
from typing import Any, Dict, List, Optional

from openhasp_config_manager.gui.domain.gui_state import (
    SCHEMA_VERSION,
    EditorTab,
    PreviewTab,
    describe_connection,
    describe_device,
    describe_editor,
    describe_problems,
    describe_tabs,
    now,
)
from openhasp_config_manager.gui.qt.window.device_tabs import PartTab


def collect_gui_state(window, running: bool = True) -> Dict[str, Any]:
    """The state for the state file (see `GuiStateFile`), as the GUI of a `MainWindow` is now."""
    editor = window.page_layout_editor_widget
    root = window.cfg_root
    session = window.session
    device = None
    problems: List[Dict[str, Any]] = []
    if session is not None and editor.session is session and session.is_loaded:
        device = describe_device(
            session,
            window.device,
            cmd=window.session_key[1],
            page=editor.current_index,
            edit_mode=editor.action_edit_mode.isChecked(),
            live_preview=editor.plate.live,
            selection=[item.obj_data for item in editor.page_preview_widget.selected_items()],
            target_component=editor.target_component,
            config_dir=root,
            part_focus=editor.part_focus,
        )
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
        "preview_command": f"openhasp-config-manager preview -c {shlex.quote(str(root))}",
        "devices": [device.name for device in window.devices],
        **describe_tabs(_preview_tabs(window), _active_index(window), root),
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


def _preview_tabs(window) -> List[PreviewTab]:
    tabs = []
    for tab in window.device_tabs.tabs:
        part = tab if isinstance(tab, PartTab) else None
        loaded = tab.device is not None and tab.editor.session is not None
        tabs.append(
            PreviewTab(
                device=tab.name,
                part=None if part is None else part.part,
                instance=None if part is None or not part.focus.is_active else part.focus.describe(),
                alone=part is not None and part.alone,
                page=tab.editor.current_index if loaded else None,
                connection=window.connections.get(tab.name).status,
                live_preview=window.connections.link(tab.name).live,
                unsaved=tab.dirty,
            )
        )
    return tabs


def _active_index(window) -> Optional[int]:
    active = window.device_tabs.active
    return None if active is None else window.device_tabs.tabs.index(active)
