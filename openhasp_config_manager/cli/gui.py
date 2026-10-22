import asyncio
import signal
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from openhasp_config_manager.gui.qt.async_bridge import setup_global_async_loop, get_global_async_loop

if TYPE_CHECKING:
    # imported in c_gui(), after the QApplication exists
    from openhasp_config_manager.gui.qt.main import MainWindow


def c_gui(config_dir: Path, output_dir: Path):
    app = QApplication(sys.argv)

    from openhasp_config_manager.gui.qt.main import create_application_settings
    from openhasp_config_manager.gui.qt.theme import apply_theme, load_theme_mode

    create_application_settings()
    apply_theme(load_theme_mode())

    # 1. Start a background thread to host the asyncio loop
    setup_global_async_loop(asyncio.new_event_loop())

    def run_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=run_loop, args=(get_global_async_loop(),), daemon=True)
    thread.start()

    # 2. Setup UI
    from openhasp_config_manager.cli.common import _create_config_manager
    from openhasp_config_manager.gui.qt.main import MainWindow

    config_manager = _create_config_manager(config_dir, output_dir)
    window = MainWindow(config_manager)
    window.show()
    _quit_on_signals(app, window)

    # 3. Standard Qt Execution (No qasync!)
    sys.exit(app.exec())


def _quit_on_signals(app: QApplication, window: "MainWindow"):
    """
    Close the window (which saves its state and stops the plate connection) and quit on SIGINT (Ctrl+C) and SIGTERM.
    """

    def _handle(_signum, _frame):
        # no dialogs from a signal handler: unsaved drafts are discarded (and logged)
        window.quit_discarding_drafts()
        app.quit()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    # Python runs signal handlers only between Python bytecodes, but Qt's event loop runs in C++: without Python code
    # running, a signal waits until the next event that happens to call into Python. This timer wakes it up regularly.
    timer = QTimer(app)
    timer.timeout.connect(lambda: None)
    timer.start(200)
