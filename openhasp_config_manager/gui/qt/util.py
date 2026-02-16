import asyncio
import functools
import logging

import qtawesome as qta

from openhasp_config_manager.openhasp_client.icons import IntegratedIcon


class IconManager:
    @staticmethod
    def get_mdi_char(icon_name: str) -> str:
        """Fetch the character from the QtAwesome MDI library."""
        try:
            # We use 'mdi6' for newer Material Design Icons
            return qta.charmap(f"mdi6.{icon_name}")
        except Exception:
            return "?"


def parse_icons(text: str) -> str:
    for unicode_char, icon_name in IntegratedIcon.entries():
        # Get the actual character QtAwesome expects for this name
        icon_char = IconManager.get_mdi_char(icon_name)

        # Replace both the :name: shorthand and the OpenHASP unicode char
        text = text.replace(f":{icon_name}:", icon_char)
        text = text.replace(unicode_char, icon_char)

    # also replace every icon supported by the mdi6 set, using the :name: syntax
    # This allows users to use any mdi6 icon without it being explicitly listed in IntegratedIcon
    # We can identify mdi6 icons by the pattern :mdi6.name:
    import re

    pattern = r":mdi6\.([a-z0-9_-]+):"

    def replace_mdi6_icon(match):
        full_name = match.group(1)  # e.g., "mdi6.home"
        icon_char = IconManager.get_mdi_char(full_name)
        return icon_char

    text = re.sub(pattern, replace_mdi6_icon, text)

    return text


def clear_layout(layout):
    """Recursively delete all widgets and layouts in the given layout."""
    if layout is None:
        return

    while layout.count():
        child = layout.takeAt(0)
        child_widget = child.widget()
        if child_widget is not None:
            child_widget.setParent(None)
            child_widget.deleteLater()
        elif child.layout() is not None:
            clear_layout(child.layout())


# We'll store the loop here so the bridge can find it
_GLOBAL_ASYNC_LOOP: asyncio.AbstractEventLoop = None


def setup_global_async_loop(loop: asyncio.AbstractEventLoop):
    global _GLOBAL_ASYNC_LOOP
    _GLOBAL_ASYNC_LOOP = loop


def get_global_async_loop() -> asyncio.AbstractEventLoop:
    if _GLOBAL_ASYNC_LOOP is None:
        raise RuntimeError("Async loop not initialized! Call setup_global_async_loop() first.")
    return _GLOBAL_ASYNC_LOOP


import threading
from typing import Awaitable, Callable, Any
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class ThreadBridge(QObject):
    """A helper to ferry function calls to the Main Thread."""

    trigger = pyqtSignal(object, tuple, dict)

    def __init__(self):
        super().__init__()
        self.trigger.connect(self._execute)

    @pyqtSlot(object, tuple, dict)
    def _execute(self, func, args, kwargs):
        func(*args, **kwargs)


# Create a single global instance of the bridge
_BRIDGE = ThreadBridge()


def run_in_main(func, *args, **kwargs):
    """
    Thread-safe way to run a function on the Qt Main Thread
    from a background asyncio thread.
    """
    if threading.current_thread() is threading.main_thread():
        func(*args, **kwargs)
    else:
        # This sends the function and args across the thread boundary
        _BRIDGE.trigger.emit(func, args, kwargs)


def qBridge(*slot_args):
    """
    Keeps the function on the Main Thread as a standard Qt Slot.
    Usage:
    @qBridge()
    def on_button_clicked(self):
        # This runs on the MAIN THREAD.


        # If you need to call async code, use run_async() to dispatch to the background loop:
        run_async(
            self.client.some_async_method(),
            on_done=self.update_ui_after_async
        )
    """

    def decorator(func):
        @pyqtSlot(*slot_args)
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # This runs on the MAIN THREAD.
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


def run_async(
    coro: Awaitable,
    on_done: Callable[[], None] = None,
    on_success: Callable[[Any], None] = None,
    on_error: Callable[[Exception], None] = None,
):
    """
    Dispatches a coroutine to the background asyncio loop.
    :param coro: The coroutine to run (e.g., client.set_page(1))
    :param on_done: Optional callback function to run on the MAIN THREAD when finished.
    :param on_success: Optional callback function to run on the MAIN THREAD if coro succeeds, receives result as argument.
    :param on_error: Optional callback function to run on the MAIN THREAD if coro raises an
    """
    loop = get_global_async_loop()

    # This wrapper handles the background execution
    async def task_wrapper():
        try:
            result = await coro

            def __run_callbacks():
                if on_success:
                    on_success(result)
                if on_done:
                    on_done()

            run_in_main(__run_callbacks)
        except Exception as ex:
            logging.exception(f"Async task failed: {ex}")
            exception = ex  # Capture the exception for use in the callback

            def __run_error_callback():
                if on_error:
                    on_error(exception)
                if on_done:
                    on_done()

            run_in_main(__run_error_callback)

    return asyncio.run_coroutine_threadsafe(task_wrapper(), loop)
