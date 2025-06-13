import asyncio
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.ui.qt.main import MainWindow


async def c_gui(config_dir: Path, output_dir: Path):
    config_manager = _create_config_manager(config_dir, output_dir)
    app = QApplication(sys.argv)
    event_loop = QEventLoop(app)
    asyncio.set_event_loop(event_loop)

    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)

    window = MainWindow(config_manager)
    window.show()

    event_loop.run_until_complete(app_close_event.wait())
    event_loop.close()
