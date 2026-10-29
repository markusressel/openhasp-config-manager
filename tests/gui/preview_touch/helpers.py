"""Helpers of the tests of touching objects in the preview."""

"""Touching the preview in Interact mode: the finger is driven through the input device, like the mouse does."""





def preview(*objects: dict, mode=None):
    from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget, PreviewMode

    view = PagePreviewWidget()
    view.set_mode(mode or PreviewMode.Interact)
    view.set_objects(list(objects))
    view.commands = []
    view.commandRequested.connect(view.commands.append)
    return view


def widget(view, object_id: int):
    from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

    return next(item for item in view.scene().items() if isinstance(item, EditableWidget) and item.data.get("id") == object_id)


def flush():
    """Commands are run from the event loop, not inside of the touch."""
    from PyQt6 import QtCore

    QtCore.QCoreApplication.processEvents()


def tap(view, x, y, now=0.0):
    view._indev.press((x, y), now)
    view._indev.release((x, y))
    flush()


BUTTON = {"page": 1, "id": 1, "obj": "btn", "x": 10, "y": 10, "w": 100, "h": 50, "text": "Go"}


DROPDOWN = {"page": 1, "id": 6, "obj": "dropdown", "x": 10, "y": 10, "w": 200, "h": 40, "options": "One\nTwo\nThree", "val": 1}


def lift(view, x, y):
    view.finger((x, y), 0.0)
    view._indev.release((x, y))
    flush()


def center(item, rect):
    point = item.mapToScene(rect.center())
    return point.x(), point.y()
