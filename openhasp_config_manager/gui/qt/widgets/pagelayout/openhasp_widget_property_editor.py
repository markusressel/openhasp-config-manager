from typing import List

from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget

from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.util import clear_layout
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget


class OpenHASPWidgetPropertyEditor(QWidget):
    """
    Displays the properties of an EditableWidget and allows the user to edit them.
    Emits a signal when a property is changed.
    """
    # Use 'object' for the value to support strings, ints, bools, etc.
    propertyChanged = QtCore.pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editable_widgets: List[EditableWidget] = []

        # Create the initial layout structure once
        self.main_layout = UiComponents.create_column(parent=self)
        self.setFixedWidth(500)  # Set a fixed width for the property editor to avoid jumping when an item is selected

        self._create_content()

    def set_editable_widgets(self, editable_widgets: List[EditableWidget]):
        """Updates the editor with new widget data."""
        # Standardize input: if None is passed, treat as empty list
        self._editable_widgets = editable_widgets

        # Clear existing widgets from the layout
        clear_layout(self.main_layout)

        # Re-populate
        self._create_content()

    def _create_content(self):
        """Populates the layout based on the current state."""
        if not self._editable_widgets:
            self.main_layout.addWidget(UiComponents.create_label("No object selected."))
            return

        if len(self._editable_widgets) > 1:
            self.main_layout.addWidget(UiComponents.create_label("Select a single object."))
            return

        editable_widget = self._editable_widgets[0]
        obj_data = editable_widget.obj_data

        # --- Header ---
        header = UiComponents.create_label(f"<b>Object ID: {obj_data.get('id', 'N/A')}</b>")
        self.main_layout.addWidget(header)

        # --- Property Rows ---
        for key, value in obj_data.items():
            # Handle X and Y specifically for display without changing the underlying dict
            if key == 'x':
                display_val = f"{value} (Live: {editable_widget.live_x})"
            elif key == 'y':
                display_val = f"{value} (Live: {editable_widget.live_y})"
            else:
                display_val = value

            self._add_property_row(key, display_val)

        # --- Actions ---
        reset_btn = UiComponents.create_button(
            title=":mdi6.undo: Reset Position",
            on_click=lambda: self._reset_position(editable_widget)
        )
        # Enable only if there's a difference to reset
        reset_btn.setEnabled(editable_widget.delta_x != 0 or editable_widget.delta_y != 0)
        self.main_layout.addWidget(reset_btn)

    def _reset_position(self, widget: EditableWidget):
        """Moves the widget back to the coordinates stored in its original data."""
        # Use the properties from your EditableWidget which pull from the dict
        widget.setPos(float(widget.obj_x), float(widget.obj_y))

        # Trigger a layout refresh to update the "Position" label and button state
        self.set_editable_widgets([widget])

    def _add_property_row(self, key, value):
        # Placeholder for property editors
        label = UiComponents.create_label(
            text=f"{key}: {value}",
        )
        self.main_layout.addWidget(label)
