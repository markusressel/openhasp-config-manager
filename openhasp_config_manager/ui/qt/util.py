import asyncio
import functools
import logging

from PyQt6.QtCore import pyqtSlot, QTimer


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


def run_in_main(func, *args, **kwargs):
    """Helper to schedule a function to run on the Qt Main Thread."""
    QTimer.singleShot(0, lambda: func(*args, **kwargs))


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


def run_async(coro, on_done=None):
    """
    Dispatches a coroutine to the background asyncio loop.
    :param coro: The coroutine to run (e.g., client.set_page(1))
    :param on_done: Optional callback function to run on the MAIN THREAD when finished.
    """
    loop = get_global_async_loop()

    # This wrapper handles the background execution
    async def task_wrapper():
        try:
            result = await coro
            if on_done:
                # Schedule the callback back on the Main Thread
                from PyQt6.QtCore import QTimer
                run_in_main(on_done, result)
        except Exception as e:
            logging.exception(f"Async task failed: {e}")

    return asyncio.run_coroutine_threadsafe(task_wrapper(), loop)
