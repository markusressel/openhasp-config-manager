def clear_layout(layout):
    """Recursively delete all widgets and layouts in the given layout."""
    if layout is not None:
        while layout.count():
            child = layout.takeAt(0)
            if child.widget() is not None:
                child.widget().setParent(None)
                child.widget().deleteLater()
            elif child.layout() is not None:
                clear_layout(child.layout())
