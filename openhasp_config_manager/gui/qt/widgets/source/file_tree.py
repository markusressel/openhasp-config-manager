from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import qtawesome as qta
from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication, QHeaderView, QLabel, QMenu, QTreeWidget, QTreeWidgetItem, QWidget, QWidgetAction

from openhasp_config_manager.gui.domain.file_operations import ConfigFiles
from openhasp_config_manager.gui.domain.file_tree import FileKind, FileNode, format_pages
from openhasp_config_manager.gui.qt.components import ThemedIcons, UiComponents
from openhasp_config_manager.gui.qt.theme import current_colors

_PATH_ROLE = Qt.ItemDataRole.UserRole
_KEY_ROLE = Qt.ItemDataRole.UserRole + 1
# whether the file matters for the plate (used, or variables); folders: whether any of their files does
_RELEVANT_ROLE = Qt.ItemDataRole.UserRole + 2

_SHOW_ALL_SETTINGS_KEY = "files/show_all"

# the file operations of the context menu (see `fileActionRequested`)
NEW_FILE = "new_file"
NEW_FOLDER = "new_folder"
RENAME = "rename"
MOVE = "move"
DELETE = "delete"
REVEAL = "reveal"

_ICONS = {
    FileKind.FOLDER: "folder-outline",
    FileKind.JSONL: "code-json",
    FileKind.CMD: "console-line",
    FileKind.VARIABLES: "variable",
    FileKind.CONFIG: "cog-outline",
}
_TARGET_ICON = "plus-circle"

# the top-level folders: (icon, the text of the second column, the explanation). The config directory itself only lists its global
# variable files, so it is named by that
_ROLE_GLOBAL = (
    "earth",
    "global",
    "Variables in the root of the config directory (theme.yaml, global.vars.yaml, ...): they apply to every file.",
)
_ROLE_COMMON = ("folder-multiple-outline", "shared", "The common folder: its files can be loaded by every device.")
_ROLE_DEVICE = (
    "tablet",
    "this device",
    "The folder of the selected device: its files are only used by this device, and its variables override the ones above.",
)
_GLOBAL_NAME = "Global variables"

# what the colors and the second column of the tree mean: (the sample, its explanation). `{accent}` is the accent color.
_LEGEND = [
    (
        '<b style="color:{accent}">name.jsonl</b>',
        "has objects on the page shown in the preview (objects on page 0, like the navbar, count for every page)",
    ),
    ("<b>name.jsonl</b> + the plus icon", "new objects are added to this file (double-click a file to choose it)"),
    ('<span style="color:gray">name.cmd</span>', "not part of the draft: the preview doesn't show objects of it"),
    (
        "<i>name.jsonl</i> (not used)",
        "no startup script (boot.cmd, online.cmd, offline.cmd) runs it. Shown with the eye button",
    ),
    ("<i>vars.yaml</i> (not used)", "none of its variables is used by a file the plate runs"),
    ("<b>config.json</b> (settings)", "the settings of the plate (WiFi, MQTT, the screen, ...), sent with every deploy"),
]
_LEGEND_COLUMN = [
    "p1, p2–p4: the pages a .jsonl file has objects on",
    "boot.cmd, ...: the startup script that loads a file that is not in the draft",
    "part: a .jsonl file that other files include (!include); the preview shows its objects with them",
    "title, theme: the variables of a variable file that are used",
    "global, shared, this device: what the top-level folders are for. The ones further down win: the variables of the device override the shared and the global ones",
]

_VARIABLES_HINT = "Variables for the templates of the files in this folder and its subfolders."
_CONFIG_HINT = (
    "The settings of the plate (WiFi, MQTT, the screen, ...). A deploy sends the ones that changed; "
    "most of them only apply after the plate restarted."
)


class FileTreeWidget(QWidget):
    """
    The folders of the config directory that hold the files of the selected device: `common` (shared by all devices)
    and the device folder. Shows which pages each .jsonl file of the draft has objects on, which files have objects on
    the current page, and which file new objects are added to.

    - Selecting a file of the draft highlights its objects in the preview (`highlightRequested`).
    - Double-clicking a file opens it in the text editor (`openRequested`). "Add new objects here" in the context menu of a
      .jsonl file of the draft makes it the target (`targetRequested`).
    - Files the plate never uses (see `used_files` and `used_variable_files`) are hidden, unless "Show all files" is on.
    - The context menu has the file operations (`fileActionRequested`): new files and folders, rename, move and delete. The
      ones that are not possible for a file (e.g. renaming `boot.cmd`) are disabled, and say why.
    """

    # the key of the component whose objects to highlight, or None
    highlightRequested = QtCore.pyqtSignal(object)
    targetRequested = QtCore.pyqtSignal(str)
    # the path of a file to edit as text
    openRequested = QtCore.pyqtSignal(object)
    # (NEW_FILE, ..., the path of the file or folder)
    fileActionRequested = QtCore.pyqtSignal(str, object)

    def __init__(self):
        super().__init__()
        layout = UiComponents.create_column(parent=self)

        header = UiComponents.create_row(alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(UiComponents.create_label("Files", role="section"), 1)
        self._show_all_button = UiComponents.create_button(
            title="",
            icon="eye-off-outline",
            on_click=lambda: self.set_show_all(self._show_all_button.isChecked()),
        )
        self._show_all_button.setCheckable(True)
        header.addWidget(self._show_all_button)
        self._legend_button = UiComponents.create_button(
            title="",
            icon="information-outline",
            tooltip="What the colors and the second column mean",
            on_click=self._show_legend,
        )
        header.addWidget(self._legend_button)
        layout.addLayout(header)

        self._hint = UiComponents.create_label("", role="hint", word_wrap=True)
        layout.addWidget(self._hint)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumHeight(120)
        self._tree.setToolTip(
            "The files of the device and the shared common folder.\n"
            "Select a file to highlight its objects, double-click it to edit it as text."
        )
        self._tree.setUniformRowHeights(True)
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        # also for the selected row: reveal() selects without highlighting
        self._tree.itemClicked.connect(lambda _item, _column: self._on_selection_changed())
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._tree, 1)

        layout.addWidget(UiComponents.create_label("Changes", role="section"))
        self._actions_row = UiComponents.create_row()
        layout.addLayout(self._actions_row)

        # resolved path -> component key, for the .jsonl files of the draft
        self._keys: Dict[Path, str] = {}
        # resolved path -> the startup script that runs it, for the .cmd and .jsonl files the plate uses
        self._used: Dict[Path, str] = {}
        # resolved path -> the referenced variables, for the variable files the used files reference
        self._used_variables: Dict[Path, List[str]] = {}
        # resolved path of a part -> the resolved paths of the files that include it
        self._includers: Dict[Path, List[Path]] = {}
        self._items_by_key: Dict[str, QTreeWidgetItem] = {}
        self._common_path: Optional[Path] = None
        self._target: Optional[str] = None
        # what is shown, to build it again when the theme changes
        self._files: Optional[tuple] = None
        self._state: Optional[tuple] = None
        self.clear()
        self.set_show_all(QSettings().value(_SHOW_ALL_SETTINGS_KEY, False, type=bool))

    def set_actions(self, actions: List[Tuple[QAction, str]]):
        """Show buttons for actions on the files (e.g. save and deploy) below the tree, as (action, mdi6 icon name)."""
        for action, icon in actions:
            button = UiComponents.create_button(
                title=action.text(), icon=icon, tooltip=action.toolTip(), on_click=action.trigger
            )
            button.setEnabled(action.isEnabled())
            action.changed.connect(lambda action=action, button=button: button.setEnabled(action.isEnabled()))
            self._actions_row.addWidget(button, 1)

    @property
    def tree(self) -> QTreeWidget:
        return self._tree

    @property
    def show_all(self) -> bool:
        return self._show_all_button.isChecked()

    def set_show_all(self, show_all: bool):
        """Show the files the plate never uses too (hidden by default)."""
        self._show_all_button.setChecked(show_all)
        ThemedIcons.apply(self._show_all_button, "eye-outline" if show_all else "eye-off-outline")
        self._show_all_button.setToolTip(
            "All files are shown: click to hide the files the plate never uses"
            if show_all
            else "Files the plate never uses are hidden (.jsonl and .cmd files no startup script runs, and variable "
            "files whose variables none of them uses): click to show them"
        )
        QSettings().setValue(_SHOW_ALL_SETTINGS_KEY, show_all)
        self._apply_filter()

    def clear(self):
        self._tree.clear()
        self._keys = {}
        self._items_by_key = {}
        self._target = None
        self._files = None
        self._state = None
        self._hint.setText("Select a device to see its files.")
        self._hint.show()

    def refresh_theme(self):
        if self._files is not None:
            self.set_files(*self._files)
        if self._state is not None:
            self.update_state(*self._state)

    def set_files(
        self,
        roots: List[FileNode],
        components: Dict[Path, str],
        used: Dict[Path, str],
        used_variables: Dict[Path, List[str]],
        includers: Dict[Path, List[Path]],
        common_path: Path,
    ):
        """
        :param roots: the folders to show (see `scan_file_tree`)
        :param components: the path of each .jsonl file of the draft -> the key of its component
        :param used: the .cmd and .jsonl files the plate runs -> the startup script that runs them (see `used_files`)
        :param used_variables: the variable files the used files reference -> the referenced variables
            (see `used_variable_files`)
        :param includers: the parts -> the files that include them (see `including_files`)
        :param common_path: the common folder: its files are shared by all devices
        """
        self._files = (roots, components, used, used_variables, includers, common_path)
        expanded = self._expanded_paths()
        self._tree.blockSignals(True)
        self._tree.clear()
        self._keys = {path.resolve(): key for path, key in components.items()}
        self._used = {path.resolve(): script for path, script in used.items()}
        self._used_variables = {path.resolve(): names for path, names in used_variables.items()}
        self._includers = {part.resolve(): [path.resolve() for path in paths] for part, paths in includers.items()}
        self._items_by_key = {}
        self._common_path = common_path.resolve()
        for root in roots:
            item = self._create_item(root, top_level=True)
            self._tree.addTopLevelItem(item)
        self._restore_expanded(expanded)
        self._apply_filter()
        self._tree.blockSignals(False)
        self._hint.hide()

    def update_state(self, pages: Dict[str, Set[int]], page: int, target: Optional[str]):
        """
        :param pages: the key of each component of the draft -> the pages it has objects on
        :param page: the page shown in the editor
        :param target: the key of the component new objects are added to
        """
        self._state = (pages, page, target)
        self._target = target
        accent = QBrush(QColor(current_colors().accent))
        target_icon = qta.icon(f"mdi6.{_TARGET_ICON}", color=QColor(current_colors().accent))
        normal = QBrush(self.palette().color(QPalette.ColorRole.Text))
        for key, item in self._items_by_key.items():
            component_pages = pages.get(key, set())
            on_page = page in component_pages or 0 in component_pages
            item.setText(1, format_pages(component_pages))
            item.setForeground(0, accent if on_page else normal)
            font = item.font(0)
            font.setBold(key == target)
            item.setFont(0, font)
            item.setIcon(0, target_icon if key == target else ThemedIcons.icon(_ICONS[FileKind.JSONL]))
            item.setToolTip(0, self._tooltip(item, key, component_pages, page))

    def reveal(self, key: Optional[str]):
        """Select the file of an object, without highlighting it (e.g. when the object is selected in the preview)."""
        item = self._items_by_key.get(key)
        if item is None:
            return
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()
        self._tree.blockSignals(True)
        self._tree.setCurrentItem(item)
        self._tree.blockSignals(False)
        self._tree.scrollToItem(item)

    # --- items ---

    def _role_of(self, node: FileNode) -> Tuple[str, str, str]:
        """:return: what a top-level folder is for (see `_ROLE_GLOBAL`)"""
        path = node.path.resolve()
        if path == self._common_path:
            return _ROLE_COMMON
        if path == self._common_path.parent:
            return _ROLE_GLOBAL
        return _ROLE_DEVICE

    def _create_item(self, node: FileNode, top_level: bool = False) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.name, ""])
        item.setData(0, _PATH_ROLE, str(node.path))
        item.setIcon(0, ThemedIcons.icon(_ICONS[node.kind]))
        if node.kind == FileKind.FOLDER:
            relevant = False
            for child in node.children:
                child_item = self._create_item(child)
                item.addChild(child_item)
                relevant |= child_item.data(0, _RELEVANT_ROLE)
            item.setData(0, _RELEVANT_ROLE, relevant)
            if top_level:
                icon, role, explanation = self._role_of(node)
                if (icon, role, explanation) == _ROLE_GLOBAL:
                    item.setText(0, _GLOBAL_NAME)
                item.setIcon(0, ThemedIcons.icon(icon))
                item.setText(1, role)
                item.setToolTip(0, f"{node.path}\n{explanation}")
            return item

        if node.kind == FileKind.CONFIG:
            item.setData(0, _RELEVANT_ROLE, True)
            item.setText(1, "settings")
            item.setToolTip(0, f"{node.path}\n{_CONFIG_HINT}")
            return item

        path = node.path.resolve()
        script = self._used.get(path)
        variables = self._used_variables.get(path)
        item.setData(0, _RELEVANT_ROLE, script is not None or variables is not None)
        key = self._keys.get(path)
        if key is not None:
            item.setData(0, _KEY_ROLE, key)
            self._items_by_key[key] = item
            return item

        includers = self._includers.get(path) if script is not None else None
        # not part of the draft: dimmed, unless it is a variable file the plate's files use, or a part the preview shows
        if not (node.kind == FileKind.VARIABLES and variables is not None) and not (
            includers is not None and self._in_preview(path)
        ):
            dimmed = QBrush(QApplication.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))
            item.setForeground(0, dimmed)
            item.setForeground(1, dimmed)
        if node.kind == FileKind.VARIABLES and variables is not None:
            used_names = f"Used: {', '.join(variables)}" if variables else "Could not be read as YAML."
            item.setText(1, ", ".join(variables) if variables else "invalid YAML")
            item.setToolTip(0, f"{_VARIABLES_HINT}\n{used_names}")
        elif node.kind == FileKind.VARIABLES:
            item.setText(1, "not used")
            item.setToolTip(0, f"{_VARIABLES_HINT}\nNone of them is used by a file the plate runs.")
            font = QFont(item.font(0))
            font.setItalic(True)
            item.setFont(0, font)
        elif script is None:
            item.setText(1, "not used")
            item.setToolTip(0, "No startup script (boot.cmd, online.cmd, offline.cmd) runs it, so the plate never uses it.")
            font = QFont(item.font(0))
            font.setItalic(True)
            item.setFont(0, font)
        elif includers is not None:
            item.setText(1, "part")
            names = ", ".join(self._display_path(including) for including in includers)
            shown = (
                "The preview shows its objects with the files that include them, read-only: change them in this file."
                if self._in_preview(path)
                else "The preview doesn't show its objects: no file of the draft includes it."
            )
            item.setToolTip(0, f"A part, included (!include) by {names} ({script}).\n{shown}")
        elif node.kind == FileKind.JSONL:
            item.setText(1, script)
            item.setToolTip(0, f"Loaded by {script} on the plate. The editor shows the pages that boot.cmd loads.")
        else:
            item.setToolTip(0, f"Run by the plate ({script}).")
        return item

    def _in_preview(self, part: Path, seen: Optional[Set[Path]] = None) -> bool:
        """:return: whether a file of the draft includes the part, directly or through other parts"""
        seen = set() if seen is None else seen
        seen.add(part)
        return any(
            including in self._keys or (including not in seen and self._in_preview(including, seen))
            for including in self._includers.get(part, [])
        )

    def _display_path(self, path: Path) -> str:
        """:return: the path of a file relative to the config directory"""
        try:
            return path.relative_to(self._common_path.parent).as_posix()
        except ValueError:
            return str(path)

    def legend_html(self) -> str:
        """:return: what the colors and the second column of the tree mean, as rich text (in the colors of the theme)"""
        accent = current_colors().accent
        rows = "".join(
            f"<tr><td style='padding-right:12px; white-space:nowrap'>{sample.format(accent=accent)}</td><td>{text}</td></tr>"
            for sample, text in _LEGEND
        )
        column = "".join(f"<li>{text}</li>" for text in _LEGEND_COLUMN)
        return f"<table>{rows}</table><p><b>Second column</b></p><ul style='margin-left:-20px'>{column}</ul>"

    def _show_legend(self):
        menu = QMenu(self)
        label = QLabel(self.legend_html())
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setMaximumWidth(460)
        label.setContentsMargins(8, 8, 8, 8)
        action = QWidgetAction(menu)
        action.setDefaultWidget(label)
        menu.addAction(action)
        menu.exec(self._legend_button.mapToGlobal(self._legend_button.rect().bottomLeft()))

    def _apply_filter(self):
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            item.setHidden(not self.show_all and not item.data(0, _RELEVANT_ROLE))
            stack.extend(item.child(i) for i in range(item.childCount()))

    def _tooltip(self, item: QTreeWidgetItem, key: str, pages: Iterable[int], page: int) -> str:
        lines = [item.data(0, _PATH_ROLE)]
        pages = set(pages)
        lines.append(f"Objects on {format_pages(pages)}" if pages else "No objects yet")
        if self._is_shared(item):
            lines.append("Shared: saving it changes the pages of every device that loads it.")
        if key == self._target:
            lines.append(f"New objects on page {page} are added to this file.")
        else:
            lines.append("Double-click to add new objects to this file.")
        return "\n".join(lines)

    def _is_shared(self, item: QTreeWidgetItem) -> bool:
        return self._common_path is not None and Path(item.data(0, _PATH_ROLE)).resolve().is_relative_to(self._common_path)

    def _expanded_paths(self) -> Optional[Set[str]]:
        """:return: the paths of the expanded folders, None if the tree is empty (everything is expanded then)"""
        if self._tree.topLevelItemCount() == 0:
            return None
        result = set()
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.isExpanded():
                result.add(item.data(0, _PATH_ROLE))
            stack.extend(item.child(i) for i in range(item.childCount()))
        return result

    def _restore_expanded(self, expanded: Optional[Set[str]]):
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.childCount() > 0:
                item.setExpanded(expanded is None or item.data(0, _PATH_ROLE) in expanded)
            stack.extend(item.child(i) for i in range(item.childCount()))

    # --- interaction ---

    def _on_selection_changed(self):
        items = self._tree.selectedItems()
        key = items[0].data(0, _KEY_ROLE) if items else None
        self.highlightRequested.emit(key)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int):
        path = Path(item.data(0, _PATH_ROLE))
        if path.is_file():
            self.openRequested.emit(path)

    def _show_context_menu(self, position: QtCore.QPoint):
        item = self._tree.itemAt(position)
        if item is None:
            return
        menu = QMenu(self)
        key = item.data(0, _KEY_ROLE)
        path = Path(item.data(0, _PATH_ROLE))
        if path.is_file():
            edit = menu.addAction(ThemedIcons.icon("file-edit-outline"), "Edit as text")
            edit.triggered.connect(lambda: self.openRequested.emit(path))
        if key is not None:
            target = menu.addAction(ThemedIcons.icon(_TARGET_ICON), "Add new objects here")
            target.setCheckable(True)
            target.setChecked(key == self._target)
            target.triggered.connect(lambda: self.targetRequested.emit(key))
            menu.addSeparator()
        self._add_file_actions(menu, path)
        menu.addSeparator()
        copy_path = menu.addAction(ThemedIcons.icon("content-copy"), "Copy path")
        copy_path.triggered.connect(lambda: QApplication.clipboard().setText(item.data(0, _PATH_ROLE)))
        reveal = menu.addAction(ThemedIcons.icon("folder-open-outline"), "Show in the file manager")
        reveal.triggered.connect(lambda: self.fileActionRequested.emit(REVEAL, path))
        menu.exec(self._tree.viewport().mapToGlobal(position))

    def file_actions(self, path: Path) -> List[Tuple[str, str, str, Optional[str]]]:
        """:return: the file operations of the context menu of a file or folder: (action, title, icon, why it is not possible)"""
        files = ConfigFiles(self._common_path.parent)
        path = path.resolve()
        result = []
        if path.is_dir():
            result.append((NEW_FILE, "New file…", "file-plus-outline", None))
            at_root = "The root of the config directory only holds variable files." if path == files.root else None
            result.append((NEW_FOLDER, "New folder…", "folder-plus-outline", at_root))
        protected = "It is the root of the config directory." if path == files.root else files.is_protected(path)
        result.append((RENAME, "Rename…", "rename-outline", protected))
        result.append((MOVE, "Move to…", "folder-move-outline", protected))
        deletion = protected if path == files.root else files.deletion_blocked(path)
        result.append((DELETE, "Delete…", "delete-outline", deletion))
        return result

    def _add_file_actions(self, menu: QMenu, path: Path):
        menu.setToolTipsVisible(True)
        for action, title, icon, reason in self.file_actions(path):
            entry = menu.addAction(ThemedIcons.icon(icon), title)
            entry.setEnabled(reason is None)
            if reason is not None:
                entry.setToolTip(reason)
            entry.triggered.connect(lambda _checked=False, action=action: self.fileActionRequested.emit(action, path))
