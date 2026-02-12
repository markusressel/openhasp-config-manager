from typing import Dict, List, Any

from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget

from openhasp_config_manager.gui.qt.components import UiComponents
from openhasp_config_manager.gui.qt.util import clear_layout


class OpenHASPWidgetPropertyEditor(QWidget):
    """
    Displays the properties of an EditableWidget and allows the user to edit them.
    Emits a signal when a property is changed.
    """
    # Use 'object' for the value to support strings, ints, bools, etc.
    propertyChanged = QtCore.pyqtSignal(str, object)

    def __init__(self, parent=None, obj_data_items=None):
        super().__init__(parent)

        # Initialize as an empty list to match the List[Dict] type hint
        if obj_data_items is None:
            obj_data_items = []
        self._obj_data_list: List[Dict[str, Any]] = obj_data_items

        # Create the initial layout structure once
        self.main_layout = UiComponents.create_column(parent=self)
        self.setFixedWidth(500)  # Set a fixed width for the property editor to avoid jumping when an item is selected

        self._create_content()

    def set_obj_data(self, data: List[Dict[str, Any]]):
        """Updates the editor with new widget data."""
        # Standardize input: if None is passed, treat as empty list
        self._obj_data_list = data

        # Clear existing widgets from the layout
        clear_layout(self.main_layout)

        # Re-populate
        self._create_content()

    def _create_content(self):
        """Populates the layout based on the current state of self._data."""

        # 1. No data or empty list
        if not self._obj_data_list:
            label = UiComponents.create_label(
                text="No properties to display",
            )
            self.main_layout.addWidget(label)
            return

        # 2. Multiple objects selected
        if len(self._obj_data_list) > 1:
            label = UiComponents.create_label(
                text="Select a single object to edit its properties.",
            )
            self.main_layout.addWidget(label)
            return

        # 3. Single object selected - show properties
        obj_data = self._obj_data_list[0]

        # Optional: Add a header with the Object ID or Type
        header = UiComponents.create_label(f"<b>Object ID: {obj_data.get('id', 'N/A')}</b>")
        self.main_layout.addWidget(header)

        for key, value in obj_data.items():
            self._add_property_editor(key, value)

    def _add_property_editor(self, key, value):
        # Placeholder for property editors
        label = UiComponents.create_label(
            text=f"{key}: {value}",
        )
        self.main_layout.addWidget(label)
