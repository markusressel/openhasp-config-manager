import asyncio

from PyQt6.QtWidgets import QMessageBox

from openhasp_config_manager.deployment import deploy_device
from openhasp_config_manager.gui.domain.draft.files import SaveConflictError, plan_save, write_save
from openhasp_config_manager.gui.qt.operations import error_text, run_busy
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.processing.variables import VariableManager


class DraftActions:
    """Save, deploy and revert the draft of the selected device of a `MainWindow`."""

    def __init__(self, window):
        self._window = window

    def save(self) -> bool:
        """
        Write the changes of the draft into the source files.
        :return: whether the draft was saved
        """
        session = self._window.session
        if session is None or not session.is_dirty:
            return False
        try:
            changes = plan_save(session)
        except (SaveConflictError, ValueError) as ex:
            QMessageBox.critical(self._window, "Save failed", error_text(ex))
            return False

        common = [change for change in changes if change.is_common]
        if common:
            paths = [change.path for change in common]
            others = sorted(
                device.name
                for device in self._window.devices
                if device.name != self._window.device.name and any(component.path in paths for component in device.jsonl)
            )
            answer = QMessageBox.question(
                self._window,
                "Save shared files",
                "These files are in the common folder and shared with other devices:\n\n"
                + "\n".join(str(path) for path in paths)
                + (f"\n\nThe change also affects: {', '.join(others)}." if others else "")
                + "\n\nSave them anyway?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Save:
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

    def deploy(self):
        """Deploy the files of the current device as they are on disk, like the deploy command of the CLI."""
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
        # its own ConfigManager: the editor may analyze the config directory at the same time (after Save)
        config_manager = ConfigManager(
            cfg_root=self._window.config_manager.cfg_root,
            output_root=self._window.config_manager.output_root,
            variable_manager=VariableManager(cfg_root=self._window.config_manager.cfg_root),
        )

        async def __deploy() -> bool:
            devices = await asyncio.to_thread(config_manager.analyze)
            device = next((device for device in devices if device.name == name), None)
            if device is None:
                raise ValueError(f"{name} is not in the config directory anymore")
            return await deploy_device(config_manager, device)

        def __on_success(changed: bool):
            if changed:
                self._window.status.succeeded.emit(f"Deployed {name}: the plate loaded the new files")
                self._window.connection.plate_restored()
            else:
                self._window.status.succeeded.emit(f"{name} is already up to date")

        run_busy(
            __deploy(),
            busy=self._window.page_layout_editor_widget.busy,
            status=self._window.status,
            description=f"Deploying the saved files of {name}",
            on_success=__on_success,
        )

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
