import copy
from contextlib import contextmanager
from typing import List, Any, Dict, Callable, Optional, Hashable, Iterator

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
    QHBoxLayout,
)

from openhasp_config_manager.gui.dimensions import UiDimensions
from openhasp_config_manager.gui.domain.properties import (
    group_properties,
    is_color_property,
    READ_ONLY_PROPERTIES,
    PIXEL_PROPERTIES,
    DIMENSION_PROPERTIES,
    is_dimension,
)
from openhasp_config_manager.gui.domain.file_tree import relative_config_path
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.domain.problems import object_name
from openhasp_config_manager.gui.qt.components import UiComponents, ThemedIcons
from openhasp_config_manager.gui.qt.layouts import clear_layout, frozen
from openhasp_config_manager.gui.qt.widgets.pagelayout.icon_picker import IconPickerDialog
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.template_completer import TemplateCompleter

# marks a property that an object does not have
_MISSING = object()

# Checks a new value of a property: (object, key, value) -> error message, or None if it is valid
type PropertyValidator = Callable[[Dict, str, Any], Optional[str]]


class OpenHASPWidgetPropertyEditor(QWidget):
    """
    Displays the properties of an EditableWidget, grouped, and allows the user to edit them.
    Invalid values are shown with an inline error and are not applied.
    """

    # (editable widget, key, value), value can be a string, int, bool, ...

    removeObjectClicked = QtCore.pyqtSignal()
    duplicateObjectClicked = QtCore.pyqtSignal()
    usePixelPositionClicked = QtCore.pyqtSignal()
    # (path, line): show a file in the text editor at a line, e.g. the part of an included object
    openSourceRequested = QtCore.pyqtSignal(object, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editable_widgets: List[EditableWidget] = []
        self._original_snapshot: Dict = {}
        self._edit_mode = False
        self._session: Optional[PlateSession] = None
        # property -> the text typed so far ("" if none), for those switched to a template that is not valid yet
        self._pending_templates: Dict[str, str] = {}
        self._validator: Optional[PropertyValidator] = None
        # whether the content was built for the current selection (it is built when the editor is created)
        self._shows_content = False
        # an edit of this panel is running (see `_edit`)
        self._applying = False

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
        self._shows_content = True

    def set_validator(self, validator: PropertyValidator):
        self._validator = validator

    def set_session(self, session: PlateSession):
        """The draft the edited objects belong to: edits change their source (literal values or templates)."""
        self._session = session

    def set_edit_mode(self, edit_mode: bool):
        """The hint without a selection depends on whether objects can be selected at all."""
        self._edit_mode = edit_mode
        if not self._editable_widgets:
            self.refresh()

    def set_editable_widgets(self, editable_widgets: List[EditableWidget]):
        """Updates the editor with new widget data."""
        if not editable_widgets and not self._editable_widgets and self._shows_content:
            # nothing is selected and nothing was: e.g. a page reloaded after an object was removed
            return
        self._editable_widgets = editable_widgets

        # Take a snapshot of the source the moment the widget is selected
        if self._editable_widgets and len(self._editable_widgets) == 1:
            self._original_snapshot = copy.deepcopy(self._session.source_of(self._editable_widgets[0].obj_data))
        else:
            self._original_snapshot = {}
        self._pending_templates = {}

        self.refresh()
        self.scroll_area.verticalScrollBar().setValue(0)

    def _create_file_label(self, obj_data: Dict) -> QWidget:
        """The file the object is defined in."""
        origin = self._session.origin_of(obj_data)
        if origin is not None:
            location = relative_config_path(origin.file, self._session.device.path)
            return UiComponents.create_label(f"{location}:{origin.line}  ·  included", role="hint", word_wrap=True)
        component = self._session.component_of(obj_data)
        location = relative_config_path(component.path, self._session.device.path)
        label = UiComponents.create_label(
            location + ("  ·  shared" if component.is_common else ""), role="hint", word_wrap=True
        )
        if component.is_common:
            label.setToolTip("A file of the common folder: saving it changes the pages of every device that loads it.")
        return label

    def refresh(self):
        """Rebuilds the editor from the current data, e.g. after the object was moved in the preview."""
        with frozen(self.content_container):
            clear_layout(self.main_layout)
            self._create_content()
            self._shows_content = True

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
            self._add_locked_position_hint()
            self._add_remove_button()
            return

        editable_widget = self._editable_widgets[0]
        obj_data = editable_widget.obj_data

        header = UiComponents.create_label(
            f"{obj_data.get('obj', '?')}  p{obj_data.get('page', '?')}b{obj_data.get('id', '?')}",
            role="title",
        )
        self.main_layout.addWidget(header)
        self.main_layout.addWidget(self._create_file_label(obj_data))
        if self._session.is_included(obj_data):
            self._add_included_content(obj_data)
            return
        self._add_locked_position_hint()

        for title, keys in group_properties(obj_data):
            group = QGroupBox(title)
            form_layout = QFormLayout(group)
            form_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for key in keys:
                form_layout.addRow(
                    self._create_property_label(key, obj_data),
                    self._create_property_field(obj_data, key, editable_widget),
                )
            self.main_layout.addWidget(group)

        self._add_reset_all_button(editable_widget, obj_data)
        self._add_duplicate_button()
        self._add_remove_button()

    def _add_included_content(self, obj_data: Dict):
        """An included object can't be changed: why, where to change it, and its properties (read-only)."""
        self.main_layout.addWidget(
            UiComponents.create_label(self._session.read_only_reason(obj_data), role="hint", word_wrap=True)
        )
        origin = self._session.origin_of(obj_data)
        directive = origin.includes[0]
        self.main_layout.addWidget(
            UiComponents.create_button(
                title="Open the part",
                icon="file-document-edit-outline",
                tooltip="Show the object in the file it is written in, where every instance of the part changes with it",
                on_click=lambda: self.openSourceRequested.emit(origin.file, origin.line),
            )
        )
        self.main_layout.addWidget(
            UiComponents.create_button(
                title="Go to the !include",
                icon="file-code-outline",
                tooltip="Show the directive that includes the part, with its vars",
                on_click=lambda: self.openSourceRequested.emit(directive.file, directive.line),
            )
        )
        source = self._session.source_of(obj_data)
        for title, keys in group_properties(obj_data):
            group = QGroupBox(title)
            form_layout = QFormLayout(group)
            form_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            for key in keys:
                value = UiComponents.create_label(str(obj_data[key]), word_wrap=True)
                value.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
                if key in source and source[key] != obj_data[key]:
                    value.setToolTip(f"In the part: {source[key]}")
                form_layout.addRow(UiComponents.create_label(f"{key}:"), value)
            self.main_layout.addWidget(group)

    def _add_hint(self, text: str):
        hint = UiComponents.create_label(text, role="hint", word_wrap=True)
        hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(hint)

    def _create_property_label(self, key: str, obj_data: Dict) -> QWidget:
        label_container = QWidget()
        label_layout = UiComponents.create_row(label_container, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        label_layout.setSpacing(UiDimensions.half)

        source = self._session.source_of(obj_data)
        has_changed = source.get(key, _MISSING) != self._original_snapshot.get(key, _MISSING)
        original = self._original_snapshot.get(key, _MISSING)
        mini_reset = UiComponents.create_button(
            title="",
            icon="undo",
            tooltip=(f"Reset {key} to {original!r}" if original is not _MISSING else f"Reset {key} to the theme default")
            if has_changed
            else None,
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
        label = UiComponents.create_label(f"{key}:")
        if key not in source:
            label.setProperty("role", "hint")
            label.setToolTip("Not in the file: a default of the theme or computed. Changing it writes it to the file.")
        label_layout.addWidget(label)
        return label_container

    def _add_locked_position_hint(self):
        """Explains why objects can't be dragged, with a button to use pixels for their position instead."""
        locked = [widget for widget in self._editable_widgets if self._session.has_computed_position(widget.obj_data)]
        if not locked:
            return
        if len(self._editable_widgets) == 1:
            text = "x or y is a template or a percentage, so the object can't be dragged."
        else:
            text = (
                f"{len(locked)} of {len(self._editable_widgets)} objects have a template or a percentage in x or y, "
                "so they can't be dragged."
            )
        self.main_layout.addWidget(UiComponents.create_label(text, role="hint", word_wrap=True))
        self.main_layout.addWidget(
            UiComponents.create_button(
                title="Use pixels for x/y",
                icon="lock-open-variant-outline",
                tooltip="Replace the templates and percentages in x and y with the pixels they show now, "
                "so the object can be moved.\nOther objects that use the same variables don't follow it anymore.",
                on_click=self.usePixelPositionClicked.emit,
            )
        )

    def _add_reset_all_button(self, editable_widget, obj_data):
        reset_btn = UiComponents.create_button(
            title="Reset All Changes",
            icon="history",
            tooltip="Restore the object as it was when it was selected",
            on_click=self._reset_all_to_snapshot,
        )

        reset_btn.setEnabled(self._session.source_of(obj_data) != self._original_snapshot)
        self.main_layout.addWidget(reset_btn)

    def _add_duplicate_button(self):
        self.main_layout.addWidget(
            UiComponents.create_button(
                title="Duplicate Object",
                icon="content-duplicate",
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
        """Restore one specific property from the snapshot (a theme default is restored by removing it again)."""
        if not self._editable_widgets:
            return
        self._restore(self._editable_widgets[0], key)
        self._pending_templates.pop(key, None)

        # Refresh UI to update the 'changed' status of reset buttons
        self.refresh()

    def _reset_all_to_snapshot(self):
        """Restores the whole object to the state it was in when selected."""
        if not self._editable_widgets:
            return

        widget = self._editable_widgets[0]
        source = self._session.source_of(widget.obj_data)
        keys = [
            key
            for key in set(source) | set(self._original_snapshot)
            if source.get(key, _MISSING) != self._original_snapshot.get(key, _MISSING)
        ]
        with self._edit(f"Reset {object_name(widget.obj_data)}"):
            for key in keys:
                self._restore_value(widget, key)
        self._pending_templates.clear()
        self.refresh()

    def _restore(self, widget: EditableWidget, key: str):
        with self._edit(f"Reset {key} of {object_name(widget.obj_data)}"):
            self._restore_value(widget, key)

    def _restore_value(self, widget: EditableWidget, key: str):
        # before the size changes, so the scene updates its index
        widget.prepareGeometryChange()
        if key in self._original_snapshot:
            self._session.set_source_value(widget.obj_data, key, copy.deepcopy(self._original_snapshot[key]))
        else:
            self._session.remove_source_value(widget.obj_data, key)

    @contextmanager
    def _edit(self, description: str, merge_key: Optional[Hashable] = None) -> Iterator[None]:
        """An edit of the draft (see `PlateSession.edit`) made by this panel: it is not rebuilt for it, see `refresh_after_change`."""
        self._applying = True
        try:
            with self._session.edit(description, merge_key=merge_key):
                yield
        finally:
            self._applying = False

    def refresh_after_change(self):
        """Show the values after the draft changed, unless this panel changed it: rebuilding it would interrupt typing."""
        if not self._applying:
            self.refresh()

    def _create_property_field(self, obj_data: Dict, key: str, widget: EditableWidget) -> QWidget:
        """The editor of a property: a literal value, or a template, switched by the button next to it."""
        template_mode = key in self._pending_templates or self._session.is_template(obj_data, key)

        container = QWidget()
        row = _plain_layout(QHBoxLayout(container))
        if template_mode:
            row.addWidget(self._create_template_editor(obj_data, key, widget), 1)
        else:
            # edit the value as written in the file (e.g. "15%"), theme defaults as rendered
            value = self._session.source_of(obj_data).get(key, obj_data[key])
            row.addWidget(self._create_editor_for_prop(obj_data, key, value, widget), 1)

        toggle = QToolButton()
        toggle.setCheckable(True)
        toggle.setChecked(template_mode)
        toggle.setAutoRaise(True)
        ThemedIcons.apply(toggle, "code-braces")
        toggle.setToolTip("Use a template (Jinja, with the variables of a deployment) instead of a value")
        toggle.toggled.connect(lambda checked: self._set_template_mode(widget, key, checked))
        toggle.setEnabled(key not in READ_ONLY_PROPERTIES)
        row.addWidget(toggle, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        return container

    def _set_template_mode(self, widget: EditableWidget, key: str, enabled: bool):
        if enabled:
            # the source changes once a valid template was entered
            self._pending_templates[key] = ""
        else:
            self._pending_templates.pop(key, None)
            if self._session.is_template(widget.obj_data, key):
                # keep the current value, as a literal
                self._on_property_edited(key, widget.obj_data.get(key), widget)
        self.refresh()

    def _create_template_editor(self, obj_data: Dict, key: str, widget: EditableWidget) -> QWidget:
        container = QWidget()
        column = _plain_layout(QVBoxLayout(container))

        source_value = self._session.source_of(obj_data).get(key)
        is_template = self._session.is_template(obj_data, key)
        editor = UiComponents.create_edittext(text=source_value if is_template else self._pending_templates.get(key, ""))
        editor.setPlaceholderText("{{ variable }}")
        editor.setToolTip("A Jinja template, rendered like a deployment does. Type to see the available variables.")
        editor.setEnabled(key not in READ_ONLY_PROPERTIES)
        TemplateCompleter(editor, self._session.template_suggestions(obj_data))
        column.addWidget(editor)

        value_label = UiComponents.create_label("", role="hint", word_wrap=True)
        error_label = UiComponents.create_label("", role="error", word_wrap=True)
        column.addWidget(value_label)
        column.addWidget(error_label)

        def show_value():
            value_label.setText(f"= {obj_data.get(key)!r}")
            value_label.setVisible(self._session.is_template(obj_data, key))

        def apply(text: str):
            if "{{" not in text:
                error = "Enter a template, e.g. {{ variable }}."
            else:
                error = self._session.check_template(obj_data, text) or self._session.check_value(obj_data, key, text)
            error_label.setText(error or "")
            error_label.setVisible(error is not None)
            if error is None:
                self._pending_templates.pop(key, None)
                self._on_property_edited(key, text, widget)
            else:
                # the panel is rebuilt e.g. after the object was moved: keep what was typed
                self._pending_templates[key] = text
            show_value()

        show_value()
        error_label.hide()
        if editor.text() and not is_template:
            apply(editor.text())
        editor.textChanged.connect(apply)
        return container

    def _create_editor_for_prop(self, obj_data: Dict, key: str, value: Any, widget: EditableWidget) -> QWidget:
        container = QWidget()
        column = _plain_layout(QVBoxLayout(container))
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

        if key in PIXEL_PROPERTIES and isinstance(value, int):
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
        if key in DIMENSION_PROPERTIES and isinstance(value, str) and value.strip().isdigit():
            value = int(value)
        error = self._validate(widget.obj_data, key, value)
        error_label.setText(error or "")
        error_label.setVisible(error is not None)
        if error is None:
            self._on_property_edited(key, value, widget)

    def _validate(self, obj_data: Dict, key: str, value: Any) -> Optional[str]:
        if is_color_property(key) and isinstance(value, str) and not QColor.isValidColorName(value):
            return "Not a color: use #RRGGBB or a color name."
        if key in DIMENSION_PROPERTIES and isinstance(value, str) and not is_dimension(value):
            return "Use pixels (e.g. 120) or a percentage of the screen (e.g. 15%)."
        if key in ("w", "h") and isinstance(value, int) and value < 1:
            return "Must be at least 1 px."
        if isinstance(value, str) and "{{" in value:
            return "This is a template: switch to template mode with the { } button."
        if self._validator is not None and (error := self._validator(obj_data, key, value)) is not None:
            return error
        return self._session.check_value(obj_data, key, value)

    def _on_property_edited(self, key, value, widget):
        """
        Sets the property in the source of the object (a value or a template) and redraws it.
        'value' can be str (from LineEdit) or int (from SpinBox).
        """
        # before the size changes, so the scene updates its index
        widget.prepareGeometryChange()
        # typing into the field is one step
        typing = ("property", self._session.object_uid(widget.obj_data), key)
        with self._edit(f"Change {key} of {object_name(widget.obj_data)}", merge_key=typing):
            self._session.set_source_value(widget.obj_data, key, value)


def _plain_layout[L: QHBoxLayout | QVBoxLayout](layout: L) -> L:
    """
    A layout without margins and without an alignment of its own: an alignment keeps word-wrapped labels in it
    (e.g. errors) from growing in height.
    """
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(UiDimensions.half)
    return layout
