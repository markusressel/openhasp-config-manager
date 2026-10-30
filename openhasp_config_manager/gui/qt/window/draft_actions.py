import asyncio
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from openhasp_config_manager.check import Issue, check_device_files
from openhasp_config_manager.deployment import OutputGenerationError, deploy_device, obsolete_files
from openhasp_config_manager.gui.domain.draft.files import FileChange, SaveConflictError, plan_save, write_save
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.qt.async_bridge import run_async
from openhasp_config_manager.gui.qt.operations import error_text, run_busy
from openhasp_config_manager.gui.qt.widgets.deploy_problems import DeployProblemsDialog
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.variables import VariableManager


class DraftActions:
    """Save, deploy and revert the draft of the selected device of a `MainWindow`."""

    def __init__(self, window):
        self._window = window

    def save(self, session: Optional[PlateSession] = None) -> bool:
        """
        Write the changes of the draft into the source files: every changed file of the `ConfigDraft`, also those the
        active tab doesn't show (like IntelliJ's Save All, they are listed first). A part on its own has a draft of its own
        (with placeholder vars, and maybe a copy of a part the shared draft has too): only its tab saves it, its part alone.
        :param session: the draft whose files to save (by default the active tab's), e.g. a part on its own whose tab closes
        :return: whether the draft was saved
        """
        session = session or self._window.session
        if session is None:
            return False
        draft = session.config if session.is_part_alone else self._window.config_draft
        try:
            changes = plan_save(draft)
        except (SaveConflictError, ValueError) as ex:
            QMessageBox.critical(self._window, "Save failed", error_text(ex))
            return False
        if not changes or not self._confirm(session, changes):
            return False

        try:
            write_save(changes)
        except OSError as ex:
            QMessageBox.critical(self._window, "Save failed", error_text(ex))
            return False
        for change in changes:
            self._window.own_writes.written(change.path.resolve(), change.content)
        # own writes are no change on disk for the watcher, but open tabs of the files must follow them
        self._window.source_editor.external_changes({change.path.resolve() for change in changes})
        # and the tabs of other devices that show them
        self._window.mark_changed_in_background_tabs({change.path.resolve() for change in changes})
        # the files are what the draft holds now: no need to load them again
        session.mark_saved({change.path: change.content for change in changes})
        self._window.status.succeeded.emit(f"Saved {len(changes)} file{'' if len(changes) == 1 else 's'}")
        return True

    def _confirm(self, session: PlateSession, changes: List[FileChange]) -> bool:
        """
        Ask before writing files the user may not expect: files that the tab doesn't show, and shared files.
        :return: whether to save
        """
        shown = self._window.shown_keys(session)
        hidden = [change for change in changes if change.key not in shown]
        common = [change for change in changes if change.is_common]
        if not hidden and not common:
            return True
        text = ""
        if hidden:
            text += "These files have changes too, which this tab doesn't show:\n\n" + "\n".join(
                session.display_paths(change.key for change in hidden)
            )
        if common:
            paths = [change.path for change in common]
            others = sorted(
                device.name
                for device in self._window.devices
                if device.name != session.device.name and any(component.path in paths for component in device.jsonl)
            )
            text += (
                ("\n\n" if text else "")
                + "These files are in the common folder and shared with other devices:\n\n"
                + "\n".join(session.display_paths(change.key for change in common))
                + (f"\n\nThe change also affects: {', '.join(others)}." if others else "")
            )
        answer = QMessageBox.question(
            self._window,
            "Save shared files" if not hidden else "Save all changed files",
            text + "\n\nSave them anyway?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Save

    def deploy(self, purge: bool = False):
        """
        Deploy the files of the current device as they are on disk, like the deploy command of the CLI.
        :param purge: also delete the files on the plate that the deployment doesn't upload (`--purge` of the CLI), after
            they were listed and the user confirmed it
        """
        if self._window.device is None:
            return
        name = self._window.device.name
        if self._window.session is not None and self._window.session.is_dirty:
            box = QMessageBox(
                QMessageBox.Icon.Question,
                "Deploy",
                f"The draft of {name} has unsaved changes. Deploy uploads only the saved files.",
                parent=self._window,
            )
            save = box.addButton("Save and deploy", QMessageBox.ButtonRole.AcceptRole)
            saved_only = box.addButton("Deploy without the changes", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(save)
            box.exec()
            if box.clickedButton() is save:
                if not self.save():
                    return
            elif box.clickedButton() is not saved_only:
                return

        # the plate shows its files after the deploy, not the draft
        self._window.page_layout_editor_widget.plate.stop_live_preview()
        # of the device deployed to, also if another tab is active when it is done
        connection = self._window.connection
        # its own ConfigManager: the editor may analyze the config directory at the same time (after Save)
        config_manager = ConfigManager(
            cfg_root=self._window.config_manager.cfg_root,
            output_root=self._window.config_manager.output_root,
            variable_manager=VariableManager(cfg_root=self._window.config_manager.cfg_root),
        )

        async def __device() -> Device:
            devices = await asyncio.to_thread(config_manager.analyze)
            device = next((device for device in devices if device.name == name), None)
            if device is None:
                raise ValueError(f"{name} is not in the config directory anymore")
            return device

        async def __deploy(delete: bool) -> bool:
            return await deploy_device(config_manager, await __device(), purge=delete)

        def __on_success(changed: bool):
            if changed:
                self._window.status.succeeded.emit(f"Deployed {name}: the plate loaded the new files")
                connection.plate_restored()
            else:
                self._window.status.succeeded.emit(f"{name} is already up to date")

        def __on_error(ex: Exception):
            if isinstance(ex, OutputGenerationError):
                self._explain_deploy_failure(config_manager, name)

        def __run(delete: bool):
            run_busy(
                __deploy(delete),
                busy=self._window.page_layout_editor_widget.busy,
                status=self._window.status,
                description=f"Deploying the saved files of {name}" + (" and removing the other files" if delete else ""),
                on_success=__on_success,
                on_error=__on_error,
            )

        if not purge:
            __run(False)
            return

        async def __obsolete() -> List[str]:
            return await obsolete_files(config_manager, await __device())

        def __on_listed(files: List[str]):
            if not files:
                self._window.status.succeeded.emit(f"{name} has no other files")
                __run(False)
            elif self.confirm_purge(name, files):
                __run(True)
            else:
                self._window.status.succeeded.emit(f"Nothing was deployed to {name}")

        run_busy(
            __obsolete(),
            busy=self._window.page_layout_editor_widget.busy,
            status=self._window.status,
            description=f"Looking for the files on {name} that the deployment doesn't upload",
            success_message=f"Listed the files of {name}",
            on_success=__on_listed,
            on_error=__on_error,
        )

    def confirm_purge(self, name: str, files: List[str]) -> bool:
        """:return: whether the user wants `files` deleted from the plate `name`"""
        box = QMessageBox(
            QMessageBox.Icon.Warning,
            "Deploy and remove other files",
            f"{name} has {len(files)} file{'' if len(files) == 1 else 's'} that the deployment doesn't upload. "
            f"Delete {'it' if len(files) == 1 else 'them'} from the plate?\n\n" + "\n".join(sorted(files)),
            parent=self._window,
        )
        delete = box.addButton("Delete and deploy", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() is delete

    def _explain_deploy_failure(self, config_manager: ConfigManager, name: str):
        """Shows every error the files of the device have (a deployment stops at the first), with how to fix them."""

        def __show(issues: List[Issue]):
            if not issues:
                return
            dialog = DeployProblemsDialog(name, Path(config_manager.cfg_root).resolve(), issues, parent=self._window)
            dialog.openRequested.connect(self._open_location)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.show()

        run_async(asyncio.to_thread(check_device_files, config_manager, name), on_success=__show)

    def _open_location(self, path: Path, line: Optional[int]):
        if line is None:
            self._window.source_sync.open_file(path)
        else:
            self._window.source_sync.open_source(path, line)

    def revert(self):
        session = self._window.session
        if session is None or not session.is_dirty:
            return
        answer = QMessageBox.question(
            self._window,
            "Revert",
            f"Discard all changes of the draft of {self._window.device.name} and load its files again?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Discard:
            self._window.reload_draft()
