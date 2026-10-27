from pathlib import Path

from PyQt6.QtWidgets import QMessageBox

from openhasp_config_manager.gui.domain.device_config_text import set_debug_ansi
from openhasp_config_manager.gui.qt.operations import BusyState, error_text, run_busy
from openhasp_config_manager.manager import CONFIG_FILE_NAME


class LogColors:
    """Turns on the colors of the log at the selected plate of a `MainWindow`: they tell the level of a log line."""

    def __init__(self, window):
        self._window = window
        self._busy = BusyState(window)

    def ask(self):
        window = self._window
        device = window.device
        if device is None:
            return
        box = QMessageBox(window)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Enable colors in the log?")
        box.setText(f"Ask {device.name} to send colors in its log?")
        box.setInformativeText(
            "openHASP tells the level of a log line (error, warning, ...) only with the color of the line. Without colors the "
            "level is guessed from the words of the line.\n\n"
            'This turns on "debug.ansi" of the plate, which also puts the colors into its serial output. It takes effect at once. '
            "A deploy sends the config.json again, so the setting is lost there unless config.json has it too."
        )
        both = box.addButton("Enable and update config.json", QMessageBox.ButtonRole.AcceptRole)
        plate_only = box.addButton("Enable on the plate only", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(both)
        box.exec()
        if box.clickedButton() in (both, plate_only):
            self.enable(update_config=box.clickedButton() is both)

    def enable(self, update_config: bool):
        """
        Turns on the colors of the log at the selected plate.
        :param update_config: also set it in the `config.json` of the device, so the next deploy keeps it
        """
        window = self._window
        device = window.device
        name = device.name
        if update_config:
            try:
                self._set_ansi_in_config_file(Path(device.path, CONFIG_FILE_NAME))
            except (OSError, ValueError) as ex:
                window.status.failed.emit(f"Updating config.json of {name}", error_text(ex))
                return
        run_busy(
            window.log_stream.set_colors(True),
            self._busy,
            window.status,
            f"Enabling colors in the log of {name}",
            success_message=f"{name} sends colors in its log now",
        )

    def _set_ansi_in_config_file(self, path: Path):
        text = path.read_text()
        changed = set_debug_ansi(text, True)
        if changed != text:
            path.write_text(changed)
            self._window.own_writes.written(path, changed)
