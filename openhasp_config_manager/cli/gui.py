import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.ui.qt.main import MainWindow


async def c_gui(config_dir: Path, output_dir: Path):
    config_manager = _create_config_manager(config_dir, output_dir)
    app = QApplication(sys.argv)

    window = MainWindow(config_manager)
    window.show()

    app.exec()
