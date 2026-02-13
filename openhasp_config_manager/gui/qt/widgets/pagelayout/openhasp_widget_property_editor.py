import copy
from typing import List, Any

from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget, QFormLayout, QLayout

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

    removeObjectClicked = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editable_widgets: List[EditableWidget] = []

        # Create the initial layout structure once
        self.main_layout = UiComponents.create_column(parent=self)
        self.setFixedWidth(500)  # Set a fixed width for the property editor to avoid jumping when an item is selected

        self._create_content()

    def set_editable_widgets(self, editable_widgets: List[EditableWidget]):
        """Updates the editor with new widget data."""
        self._editable_widgets = editable_widgets

        # Take a snapshot of the data the moment the widget is selected
        if self._editable_widgets and len(self._editable_widgets) == 1:
            self._original_snapshot = copy.deepcopy(self._editable_widgets[0].obj_data)
        else:
            self._original_snapshot = {}

        clear_layout(self.main_layout)
        self._create_content()

    def _create_content(self):
        if not self._editable_widgets:
            self.main_layout.addWidget(UiComponents.create_label("No object selected."))
            return

        if len(self._editable_widgets) > 1:
            self.main_layout.addWidget(UiComponents.create_label("Select a single object."))
            return

        editable_widget = self._editable_widgets[0]
        obj_data = editable_widget.obj_data

        # Header
        header = UiComponents.create_label(f"<b>Object ID: {obj_data.get('id', 'N/A')}</b>")
        self.main_layout.addWidget(header)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        for key, value in obj_data.items():
            # 1. Create the container widget
            label_container = QWidget()
            # Important: Use the layout to drive the container size
            label_layout = UiComponents.create_row(label_container)
            label_layout.setContentsMargins(0, 0, 0, 0)
            label_layout.setSpacing(2)
            # Force the container to respect the size of the children
            label_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

            # 2. Create Reset Button
            mini_reset = UiComponents.create_button(
                title=":mdi6.undo:",
                on_click=lambda k=key: self._reset_single_property(k)
            )
            mini_reset.setFixedSize(22, 22)

            # 3. Logic to check if value actually changed
            original_val = self._original_snapshot.get(key)
            # Compare as strings to be safe against type mismatches
            has_changed = str(value) != str(original_val)

            # DEBUG: For now, let's keep it visible but change color to see it
            if has_changed:
                mini_reset.setStyleSheet("color: #FF5722; background: transparent; border: none; font-size: 14px;")
                mini_reset.setEnabled(True)
            else:
                # If not changed, make it a faint gray so we know it's THERE but inactive
                mini_reset.setStyleSheet("color: rgba(200, 200, 200, 50); background: transparent; border: none; font-size: 14px;")
                mini_reset.setEnabled(False)

            label_text = UiComponents.create_label(text=f"{key}:", padding=0)

            label_layout.addWidget(mini_reset)
            label_layout.addWidget(label_text)

            # 4. Add to the form
            editor_widget = self._create_editor_for_prop(key, value, editable_widget)
            form_layout.addRow(label_container, editor_widget)

        self.main_layout.addLayout(form_layout)

        self._add_reset_all_button(editable_widget, obj_data)
        self._add_remove_button()

    def _add_reset_all_button(self, editable_widget, obj_data):
        reset_btn = UiComponents.create_button(
            title=":mdi6.history: Reset All Changes",
            on_click=self._reset_all_to_snapshot
        )

        # Enable if any property differs from the snapshot OR if it has moved from original obj_x/y
        any_changes = obj_data != self._original_snapshot
        reset_btn.setEnabled(any_changes or editable_widget.delta_x != 0 or editable_widget.delta_y != 0)
        self.main_layout.addWidget(reset_btn)

    def _add_remove_button(self):
        remove_btn = UiComponents.create_button(
            title=":mdi6.delete: Remove Object",
            on_click=lambda: self.removeObjectClicked.emit()
        )
        remove_btn.setStyleSheet("background-color: red; color: white;")
        self.main_layout.addWidget(remove_btn)

    def _reset_single_property(self, key):
        """Restore one specific property from the snapshot."""
        if not self._editable_widgets or key not in self._original_snapshot:
            return

        widget = self._editable_widgets[0]
        original_value = self._original_snapshot[key]

        # Apply change
        self._on_property_edited(key, original_value, widget)

        # Refresh UI to update the 'changed' status of reset buttons
        self.set_editable_widgets([widget])

    def _reset_all_to_snapshot(self):
        """Restores the whole object to the state it was in when selected."""
        if not self._editable_widgets:
            return

        widget = self._editable_widgets[0]
        # Update current data with snapshot data
        widget.obj_data.update(copy.deepcopy(self._original_snapshot))

        # Sync physical position
        widget.setPos(float(widget.obj_x), float(widget.obj_y))
        widget.prepareGeometryChange()
        widget.update()

        # Refresh UI
        self.set_editable_widgets([widget])

    def _create_editor_for_prop(self, key: str, value: Any, widget):
        container = QWidget()
        layout = UiComponents.create_row(container, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(0, 0, 0, 0)

        # Determine which widget to use
        is_numeric = key in ['x', 'y', 'w', 'h', 'border_width', 'radius', 'id', 'page', 'outline_width', 'icon_size']

        if is_numeric:
            # Create a SpinBox for numbers
            editor = UiComponents.create_spinbox(initial_value=int(value), min_val=0)
            # QSpinBox uses valueChanged[int] instead of textChanged
            editor.valueChanged.connect(lambda val: self._on_property_edited(key, val, widget))
        else:
            # Keep Edittext for strings/colors
            editor = UiComponents.create_edittext(text=str(value))
            editor.textChanged.connect(lambda text: self._on_property_edited(key, text, widget))

        # Handle read-only logic
        if key in ['page', 'obj']:
            editor.setEnabled(False)  # SpinBoxes use setEnabled(False) or setReadOnly(True)

        layout.addWidget(editor)

        # --- Handle Units (px) ---
        if key in ['x', 'y', 'w', 'h', 'border_width', 'radius']:
            unit_label = UiComponents.create_label("px")
            unit_label.setStyleSheet("color: gray;")
            layout.addWidget(unit_label)

            if key in ['x', 'y']:
                live_val = widget.live_x if key == 'x' else widget.live_y
                live_label = UiComponents.create_label(f"(Live: {live_val})")
                live_label.setStyleSheet("color: #0078d7;")
                layout.addWidget(live_label)

        # --- Handle Colors ---
        if "color" in key and isinstance(value, str) and value.startswith("#"):
            editor.setStyleSheet(f"border-right: 10px solid {value}; padding-right: 5px;")
            editor.setMaxLength(7)

        return container

    def _on_property_edited(self, key, value, widget):
        """Updates the internal data. 'value' can be str (from LineEdit) or int (from SpinBox)."""
        # Update the underlying dict
        widget.obj_data[key] = value

        # If position changed, update the QGraphicsObject immediately
        if key == 'x' or key == 'y':
            widget.setPos(float(widget.obj_x), float(widget.obj_y))

        # If size changed (w, h), notify the scene
        if key in ['w', 'h']:
            widget.prepareGeometryChange()

        widget.update()
        self.propertyChanged.emit(key, value)

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
