from contextlib import contextmanager


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


@contextmanager
def frozen(widget):
    """Don't repaint a widget (and its children) while it is changed in several steps, so the steps don't show as flicker."""
    widget.setUpdatesEnabled(False)
    try:
        yield
    finally:
        widget.setUpdatesEnabled(True)
