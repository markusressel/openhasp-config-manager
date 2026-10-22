import copy
from typing import List, Any, Dict, Callable, Optional

from PyQt6 import QtCore
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget,
    QFormLayout,
    QScrollArea,
    QVBoxLayout,
    QFrame,
    QGroupBox,
    QCheckBox,
    QColorDialog,
    QToolButton,
    QLineEdit,
    QLabel,
)

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.properties import (
    group_properties,
    is_color_property,
    READ_ONLY_PROPERTIES,
    PIXEL_PROPERTIES,
)
from openhasp_config_manager.gui.qt.components import UiComponents, ThemedIcons
from openhasp_config_manager.gui.qt.util import clear_layout
from openhasp_config_manager.gui.qt.widgets.pagelayout.icon_picker import IconPickerDialog
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

# Checks a new value of a property: (object, key, value) -> error message, or None if it is valid
type PropertyValidator = Callable[[Dict, str, Any], Optional[str]]


class OpenHASPWidgetPropertyEditor(QWidget):
    """
    Displays the properties of an EditableWidget, grouped, and allows the user to edit them.
    Invalid values are shown with an inline error and are not applied.
    """

    # (editable widget, key, value), value can be a string, int, bool, ...
    propertyChanged = QtCore.pyqtSignal(object, str, object)

    removeObjectClicked = QtCore.pyqtSignal()
    duplicateObjectClicked = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editable_widgets: List[EditableWidget] = []
        self._original_snapshot: Dict = {}
        self._edit_mode = False
        self._validator: Optional[PropertyValidator] = None

        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)

        # Scroll Area to contain the form (important for many properties)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)  # Crucial for internal layout to expand
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.content_container = QWidget()
        self.main_layout = UiComponents.create_column(
            parent=self.content_container,
            margin_start=UiDimensions.one,
            margin_end=UiDimensions.one,
            margin_top=UiDimensions.one,
            margin_bottom=UiDimensions.one,
        )
        self.setMinimumWidth(280)

        self.scroll_area.setWidget(self.content_container)
        self.outer_layout.addWidget(self.scroll_area)

        self._create_content()

    def set_validator(self, validator: PropertyValidator):
        self._validator = validator

    def set_edit_mode(self, edit_mode: bool):
        """The hint without a selection depends on whether objects can be selected at all."""
        self._edit_mode = edit_mode
        if not self._editable_widgets:
            self.refresh()

    def set_editable_widgets(self, editable_widgets: List[EditableWidget]):
        """Updates the editor with new widget data."""
        self._editable_widgets = editable_widgets

        # Take a snapshot of the data the moment the widget is selected
        if self._editable_widgets and len(self._editable_widgets) == 1:
            self._original_snapshot = copy.deepcopy(self._editable_widgets[0].obj_data)
        else:
            self._original_snapshot = {}

        self.refresh()
        self.scroll_area.verticalScrollBar().setValue(0)

    def refresh(self):
        """Rebuilds the editor from the current data, e.g. after the object was moved in the preview."""
        clear_layout(self.main_layout)
        self._create_content()

    def _create_content(self):
        if not self._editable_widgets:
            if self._edit_mode:
                hint = "Select an object on the plate to edit its properties."
            else:
                hint = "Switch to edit mode (Ctrl+E) to select and change objects."
            self._add_hint(hint)
            return

        if len(self._editable_widgets) > 1:
            self._add_hint(f"{len(self._editable_widgets)} objects selected. Select a single object to edit its properties.")
            self._add_remove_button()
            return

        editable_widget = self._editable_widgets[0]
        obj_data = editable_widget.obj_data

        header = UiComponents.create_label(
            f"{obj_data.get('obj', '?')}  p{obj_data.get('page', '?')}b{obj_data.get('id', '?')}",
            role="title",
        )
        self.main_layout.addWidget(header)

        for title, keys in group_properties(obj_data):
            group = QGroupBox(title)
            form_layout = QFormLayout(group)
            form_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for key in keys:
                form_layout.addRow(
                    self._create_property_label(key, obj_data),
                    self._create_editor_for_prop(obj_data, key, obj_data[key], editable_widget),
                )
            self.main_layout.addWidget(group)

        self._add_reset_all_button(editable_widget, obj_data)
        self._add_duplicate_button()
        self._add_remove_button()

    def _add_hint(self, text: str):
        hint = UiComponents.create_label(text, role="hint", word_wrap=True)
        hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(hint)

    def _create_property_label(self, key: str, obj_data: Dict) -> QWidget:
        label_container = QWidget()
        label_layout = UiComponents.create_row(label_container, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        label_layout.setSpacing(UiDimensions.half)

        has_changed = str(obj_data[key]) != str(self._original_snapshot.get(key))
        mini_reset = UiComponents.create_button(
            title="",
            icon="undo",
            tooltip=f"Reset {key} to {self._original_snapshot.get(key)!r}" if has_changed else None,
            variant="flat",
            on_click=lambda k=key: self._reset_single_property(k),
        )
        mini_reset.setFixedSize(UiDimensions.three, UiDimensions.three)
        # keeps the labels aligned, but only shows the button for changed properties
        policy = mini_reset.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        mini_reset.setSizePolicy(policy)
        mini_reset.setVisible(has_changed)

        label_layout.addWidget(mini_reset)
        label_layout.addWidget(UiComponents.create_label(f"{key}:"))
        return label_container

    def _add_reset_all_button(self, editable_widget, obj_data):
        reset_btn = UiComponents.create_button(
            title="Reset All Changes",
            icon="history",
            tooltip="Restore the object as it was when it was selected",
            on_click=self._reset_all_to_snapshot,
        )

        # Enable if any property differs from the snapshot OR if it has moved from original obj_x/y
        any_changes = obj_data != self._original_snapshot
        reset_btn.setEnabled(any_changes or editable_widget.delta_x != 0 or editable_widget.delta_y != 0)
        self.main_layout.addWidget(reset_btn)

    def _add_duplicate_button(self):
        self.main_layout.addWidget(
            UiComponents.create_button(
                title="Duplicate Object",
                icon="content-copy",
                tooltip="Duplicate the object (Ctrl+D)",
                on_click=self.duplicateObjectClicked.emit,
            )
        )

    def _add_remove_button(self):
        self.main_layout.addWidget(
            UiComponents.create_button(
                title="Remove Object" if len(self._editable_widgets) == 1 else "Remove Objects",
                icon="delete",
                tooltip="Remove from the page (Del)",
                variant="danger",
                on_click=self.removeObjectClicked.emit,
            )
        )

    def _reset_single_property(self, key):
        """Restore one specific property from the snapshot."""
        if not self._editable_widgets or key not in self._original_snapshot:
            return

        widget = self._editable_widgets[0]
        original_value = self._original_snapshot[key]

        # Apply change
        self._on_property_edited(key, original_value, widget)

        # Refresh UI to update the 'changed' status of reset buttons
        self.refresh()

    def _reset_all_to_snapshot(self):
        """Restores the whole object to the state it was in when selected."""
        if not self._editable_widgets:
            return

        widget = self._editable_widgets[0]
        for key, value in copy.deepcopy(self._original_snapshot).items():
            if widget.obj_data.get(key) != value:
                self._on_property_edited(key, value, widget)

        # Sync physical position
        widget.setPos(float(widget.obj_x), float(widget.obj_y))

        self.refresh()

    def _create_editor_for_prop(self, obj_data: Dict, key: str, value: Any, widget: EditableWidget) -> QWidget:
        container = QWidget()
        column = UiComponents.create_column(container)
        column.setSpacing(UiDimensions.half)
        row = UiComponents.create_row(alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        column.addLayout(row)

        error_label = UiComponents.create_label("", role="error", word_wrap=True)
        error_label.hide()

        def apply(new_value: Any):
            self._apply_value(widget, key, new_value, error_label)

        if isinstance(value, bool):
            editor = QCheckBox()
            editor.setChecked(value)
            editor.toggled.connect(apply)
            row.addWidget(editor)
        elif isinstance(value, int):
            max_value = int(obj_data["h"] / 2) if key == "radius" and "h" in obj_data else None
            editor = UiComponents.create_spinbox(initial_value=value, min_val=0, max_val=max_value)
            editor.valueChanged.connect(apply)
            row.addWidget(editor, 1)
        elif is_color_property(key):
            editor = self._create_color_editor(str(value), apply, row)
        else:
            editor = UiComponents.create_edittext(text=str(value))
            editor.textChanged.connect(apply)
            row.addWidget(editor, 1)
            if key == "text":
                row.addWidget(self._create_icon_insert_button(editor))

        if key in READ_ONLY_PROPERTIES:
            editor.setEnabled(False)

        if key in PIXEL_PROPERTIES:
            row.addWidget(UiComponents.create_label("px", role="hint"))

        column.addWidget(error_label)
        return container

    def _create_color_editor(self, value: str, apply: Callable[[Any], None], row) -> QLineEdit:
        editor = UiComponents.create_edittext(text=value)
        editor.setPlaceholderText("#RRGGBB or a color name")
        row.addWidget(editor, 1)

        swatch = QToolButton()
        swatch.setToolTip("Pick a color")
        swatch.setFixedSize(UiDimensions.four, UiDimensions.three + UiDimensions.half)

        def update_swatch(text: str):
            color = QColor(text) if QColor.isValidColorName(text) else None
            # the swatch shows a value, not a theme color
            swatch.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid palette(mid);"
                if color
                else "border: 1px dashed palette(mid);"
            )

        def pick_color():
            initial = QColor(editor.text()) if QColor.isValidColorName(editor.text()) else QColor("white")
            color = QColorDialog.getColor(initial, self, "Pick a color")
            if color.isValid():
                editor.setText(color.name().upper())

        def on_text_changed(text: str):
            update_swatch(text)
            apply(text)

        update_swatch(value)
        swatch.clicked.connect(pick_color)
        editor.textChanged.connect(on_text_changed)
        row.addWidget(swatch)
        return editor

    def _create_icon_insert_button(self, editor: QLineEdit) -> QToolButton:
        button = QToolButton()
        ThemedIcons.apply(button, "emoticon-outline")
        button.setToolTip("Insert an openHASP icon")

        def insert_icon():
            char = IconPickerDialog.pick(self)
            if char is not None:
                editor.insert(char)
                editor.setFocus()

        button.clicked.connect(insert_icon)
        return button

    def _apply_value(self, widget: EditableWidget, key: str, value: Any, error_label: QLabel):
        error = self._validate(widget.obj_data, key, value)
        error_label.setText(error or "")
        error_label.setVisible(error is not None)
        if error is None:
            self._on_property_edited(key, value, widget)

    def _validate(self, obj_data: Dict, key: str, value: Any) -> Optional[str]:
        if is_color_property(key) and isinstance(value, str) and not QColor.isValidColorName(value):
            return "Not a color: use #RRGGBB or a color name."
        if key in ("w", "h") and value < 1:
            return "Must be at least 1 px."
        if self._validator is not None:
            return self._validator(obj_data, key, value)
        return None

    def _on_property_edited(self, key, value, widget):
        """Updates the internal data. 'value' can be str (from LineEdit) or int (from SpinBox)."""
        # Update the underlying dict
        widget.obj_data[key] = value

        # If position changed, update the QGraphicsObject immediately
        if key == "x" or key == "y":
            widget.setPos(float(widget.obj_x), float(widget.obj_y))

        # If size changed (w, h), notify the scene
        if key in ["w", "h"]:
            widget.prepareGeometryChange()

        widget.update()
        self.propertyChanged.emit(widget, key, value)
