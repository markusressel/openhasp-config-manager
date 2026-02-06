import asyncio
import sys
from pathlib import Path

import qt_themes
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.ui.qt.main import MainWindow


def c_gui(config_dir: Path, output_dir: Path):
    """The synchronous entry point called by your Click CLI."""
    app = QApplication(sys.argv)

    # 1. Create the loop but DON'T start it with run_until_complete
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # 2. Setup the UI and the logic
    qt_themes.set_theme('one_dark_two')
    config_manager = _create_config_manager(config_dir, output_dir)

    window = MainWindow(config_manager)
    window.show()

    with loop:
        loop.run_forever()
