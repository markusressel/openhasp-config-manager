import asyncio
import sys
import threading
from pathlib import Path

import qt_themes
from PyQt6.QtWidgets import QApplication

from openhasp_config_manager.ui.qt.util import setup_global_async_loop, get_global_async_loop


def c_gui(config_dir: Path, output_dir: Path):
    app = QApplication(sys.argv)
    qt_themes.set_theme('one_dark_two')

    # 1. Start a background thread to host the asyncio loop
    setup_global_async_loop(asyncio.new_event_loop())

    def run_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=run_loop, args=(get_global_async_loop(),), daemon=True)
    thread.start()

    # 2. Setup UI
    from openhasp_config_manager.cli.common import _create_config_manager
    from openhasp_config_manager.ui.qt.main import MainWindow

    config_manager = _create_config_manager(config_dir, output_dir)
    window = MainWindow(config_manager)
    window.show()

    # 3. Standard Qt Execution (No qasync!)
    sys.exit(app.exec())
