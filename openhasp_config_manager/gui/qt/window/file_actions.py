from html import escape
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QFile, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QCheckBox, QInputDialog, QLineEdit, QMessageBox

from openhasp_config_manager.gui.domain.file_operations import (
    ConfigFiles,
    FileOperationError,
    FilePlan,
    apply_plan,
    move_targets,
    plan_create,
    plan_delete,
    plan_move,
)
from openhasp_config_manager.gui.qt.operations import error_text
from openhasp_config_manager.gui.qt.widgets.source.file_tree import DELETE, MOVE, NEW_FILE, NEW_FOLDER, RENAME, REVEAL


class FileActions:
    """
    New files and folders, rename, move and delete in the Files tree of a `MainWindow` (see `file_operations`). The pages
    follow the files on disk afterwards, like after any other change on disk.
    """

    def __init__(self, window):
        self._window = window

    def request(self, action: str, path: Path):
        handlers = {
            NEW_FILE: self.new_file,
            NEW_FOLDER: self.new_folder,
            RENAME: self.rename,
            MOVE: self.move,
            DELETE: self.delete,
            REVEAL: self.reveal,
        }
        handlers[action](path)

    @property
    def _files(self) -> ConfigFiles:
        return ConfigFiles(Path(self._window.config_manager.cfg_root))

    def new_file(self, folder: Path):
        files = self._files
        default = "new.yaml" if folder.resolve() == files.root else "new.jsonl"
        name = self._ask_name("New file", "Name of the new file (.jsonl, .cmd or .yaml):", default)
        if name is None:
            return
        boot = None if self._window.device is None else Path(self._window.device.path, "boot.cmd")
        run = QCheckBox(f"Run it from boot.cmd of {self._window.device.name}") if boot is not None else None
        if run is not None:
            run.setChecked(True)
        # whether boot.cmd runs it is only asked for a page file
        if run is None or not name.endswith(".jsonl") or not boot.is_file():
            self._run(f"New file {name}", lambda: plan_create(files, folder, name), confirm=None, open_new=True)
            return
        self._run(
            f"New file {name}",
            lambda: plan_create(files, folder, name, run_from=boot if run.isChecked() else None),
            confirm="Create",
            open_new=True,
            check_box=run,
        )

    def new_folder(self, parent: Path):
        name = self._ask_name("New folder", "Name of the new folder:", "new_folder")
        if name is not None:
            self._run(f"New folder {name}", lambda: plan_create(self._files, parent, name), confirm=None)

    def rename(self, path: Path):
        name = self._ask_name("Rename", f"New name of {path.name}:", path.name)
        if name is not None and name != path.name:
            self._run(f"Rename {path.name}", lambda: plan_move(self._files, path, path.parent / name), confirm="Rename")

    def move(self, path: Path):
        files = self._files
        if self._window.device is None:
            return
        targets = move_targets(files, path, Path(self._window.device.path))
        if not targets:
            QMessageBox.information(self._window, "Move", f"There is no other folder to move {path.name} to.")
            return
        names = [_folder_name(files, target) for target in targets]
        name, ok = QInputDialog.getItem(self._window, "Move", f"Move {path.name} to:", names, 0, False)
        if ok:
            target = targets[names.index(name)] / path.name
            self._run(f"Move {path.name}", lambda: plan_move(files, path, target), confirm="Move")

    def delete(self, path: Path):
        self._run(f"Delete {path.name}", lambda: plan_delete(self._files, path), confirm="Move to trash")

    @staticmethod
    def reveal(path: Path):
        """Show the folder (of a file) in the file manager."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))

    # --- internals ---

    def _ask_name(self, title: str, label: str, default: str) -> Optional[str]:
        name, ok = QInputDialog.getText(self._window, title, label, QLineEdit.EchoMode.Normal, default)
        return name.strip() if ok else None

    def _run(
        self,
        title: str,
        build: Callable[[], FilePlan],
        confirm: Optional[str],
        open_new: bool = False,
        check_box: Optional[QCheckBox] = None,
    ):
        """
        Make the plan, show it and ask (unless `confirm` is None), carry it out, and let the editor follow it.
        :param title: what is done, e.g. "Delete page.jsonl", for the dialogs
        :param confirm: the text of the button that carries it out
        :param check_box: an option of the plan, shown in the question: the plan is made again with it after the answer
        """
        try:
            plan = build()
        except FileOperationError as ex:
            self._refuse(title, ex)
            return
        blocked = self._blocked(plan)
        if blocked is not None:
            QMessageBox.warning(self._window, plan.description, blocked)
            return
        if confirm is not None:
            box = QMessageBox(
                QMessageBox.Icon.Question,
                plan.description,
                plan.description + "?" + "".join(f"\n\n{note}" for note in plan.notes),
                parent=self._window,
            )
            accept = box.addButton(confirm, QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(accept)
            if check_box is not None:
                box.setCheckBox(check_box)
            box.exec()
            if box.clickedButton() is not accept:
                return
            if check_box is not None:
                try:
                    plan = build()
                except FileOperationError as ex:
                    self._refuse(title, ex)
                    return
        try:
            apply_plan(plan, _move_to_trash)
        except OSError as ex:
            QMessageBox.critical(self._window, plan.description, error_text(ex))
            return
        self._follow(plan, open_new)
        self._window.status.succeeded.emit(plan.description)

    def _refuse(self, title: str, error: FileOperationError):
        """Say why an operation is not possible, with a button for each file to change first: it opens at the first line."""
        box = QMessageBox(
            QMessageBox.Icon.Warning, f"{title}: not possible", f"<b>{escape(error.summary, quote=False)}</b>", parent=self._window
        )
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setInformativeText(_details_html(error))
        files = ConfigFiles(Path(self._window.config_manager.cfg_root))
        first_lines = {}
        for reference in error.references:
            first_lines.setdefault(reference.file, reference)
        names = [file.name for file in first_lines]
        opening = {}
        for file, reference in list(first_lines.items())[:_MAX_OPEN_BUTTONS]:
            # boot.cmd of two devices: name them by their path
            name = file.name if names.count(file.name) == 1 else files.config_path(file)
            opening[box.addButton(f"Open {name}", QMessageBox.ButtonRole.ActionRole)] = reference
        box.setDefaultButton(box.addButton(QMessageBox.StandardButton.Close))
        box.exec()
        reference = opening.get(box.clickedButton())
        if reference is not None:
            self._window.source_sync.open_source(reference.file, reference.line)

    def _blocked(self, plan: FilePlan) -> Optional[str]:
        """:return: why the plan can't be carried out now: unsaved changes in the files it changes"""
        touched = plan.touched
        session = self._window.session
        if session is not None and session.is_dirty:
            draft_files = [component.path.resolve() for component in session.components]
            if any(_within(path, touched) for path in draft_files):
                return "The draft has unsaved changes in files this changes. Save or revert the draft first."
        unsaved = [path for path in self._window.source_editor.dirty_files() if _within(path.resolve(), touched)]
        if unsaved:
            return f"The text editor has unsaved changes in {', '.join(path.name for path in unsaved)}. Save them first."
        return None

    def _follow(self, plan: FilePlan, open_new: bool):
        """The text editor and the pages follow the plan that was carried out."""
        editor = self._window.source_editor
        for path in editor.open_files:
            path = path.resolve()
            for source, target in plan.moves:
                if path == source or path.is_relative_to(source):
                    editor.close_tab(path, ask=False)
                    editor.open_file(target / path.relative_to(source) if path != source else target, focus=False)
            if any(path == deleted or path.is_relative_to(deleted) for deleted in plan.deletes):
                editor.close_tab(path, ask=False)
        if open_new:
            for path, content in plan.creates:
                if content is not None:
                    self._window.source_sync.open_file(path)
        editor.external_changes(set(plan.edits))
        if self._window.device is not None:
            self._window.reload_files(plan.touched)


def _details_html(error: FileOperationError) -> str:
    """:return: the explanation, each line (in a monospace font, its place below it) and the advice"""
    lines = "".join(
        f"<p style='margin-left:12px'><code>{escape(reference.text, quote=False)}</code><br>"
        f"<span style='color:gray'>{escape(reference.location, quote=False)}</span></p>"
        for reference in error.references
    )
    parts = [f"<p>{escape(error.explanation, quote=False)}</p>" if error.explanation else "", lines]
    parts.append(f"<p>{escape(error.advice, quote=False)}</p>" if error.advice else "")
    return "".join(parts)


# more files to change are listed, but get no button
_MAX_OPEN_BUTTONS = 3


def _within(path: Path, roots: set) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


def _folder_name(files: ConfigFiles, folder: Path) -> str:
    return f"{files.root.name} (the root: global variables)" if folder == files.root else files.config_path(folder)


def _move_to_trash(path: Path):
    """:raises OSError: if the file can't be moved to the trash (it is not deleted then)"""
    result = QFile.moveToTrash(str(path))
    moved = result[0] if isinstance(result, tuple) else result
    if not moved:
        raise OSError(f"{path} could not be moved to the trash.")

