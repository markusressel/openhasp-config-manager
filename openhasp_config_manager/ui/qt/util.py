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
