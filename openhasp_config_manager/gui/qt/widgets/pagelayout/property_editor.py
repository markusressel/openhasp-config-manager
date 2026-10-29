import copy
import json
import keyword
import re
from contextlib import contextmanager
from typing import List, Any, Dict, Callable, Optional, Hashable, Iterator, Tuple, Union

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
    QComboBox,
    QSizePolicy,
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
from openhasp_config_manager.gui.domain.draft.part_focus import PartFocus
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.domain.problems import Severity, object_name
from openhasp_config_manager.gui.domain.source.docs import property_help
from openhasp_config_manager.processing.jsonl.includes import FOR, INCLUDE, INCLUDE_KEYS, VARS, IncludeStep
from openhasp_config_manager.gui.qt.components import UiComponents, ThemedIcons
from openhasp_config_manager.gui.qt.layouts import clear_layout, frozen
from openhasp_config_manager.gui.qt.widgets.pagelayout.icon_picker import IconPickerDialog
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.gui.qt.widgets.hover_card import CardContent
from openhasp_config_manager.gui.qt.widgets.pagelayout.property_hover import PropertyLabelHover
from openhasp_config_manager.gui.qt.widgets.pagelayout.template_completer import TemplateCompleter
from openhasp_config_manager.validation.property_values import matching_choice, value_choices

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
    # an included object: edit its part in part mode, in the instance of the object
    editPartRequested = QtCore.pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editable_widgets: List[EditableWidget] = []
        self._original_snapshot: Dict = {}
        self._edit_mode = False
        self._session: Optional[PlateSession] = None
        # the part mode of the editor, None outside of part mode
        self._part_focus: Optional[PartFocus] = None
        # property -> the text typed so far ("" if none), for those switched to a template that is not valid yet
        self._pending_templates: Dict[str, str] = {}
        self._validator: Optional[PropertyValidator] = None
        # whether the content was built for the current selection (it is built when the editor is created)
        self._shows_content = False
        # an edit of this panel is running (see `_edit`)
        self._applying = False
        # (vars or for, name) of the fields of an `!include` switched to a template that was not applied yet -> the text
        self._pending_directive_templates: Dict[Tuple[str, str], str] = {}
        # the field of an `!include` that was edited last, to type on in it when the panel is made again for the same object
        # (e.g. because the edit added objects): (object, vars or for, name, cursor position)
        self._directive_focus: Optional[Tuple[Dict, str, str, int]] = None
        # what shows values of the selected object that an edit of this panel changes, without making the panel again
        self._value_updates: List[Callable[[], None]] = []

        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)

        # Scroll Area to contain the form (important for many properties)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)  # Crucial for internal layout to expand
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        # only when the dock is narrower than the fields need: everything stays reachable
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)

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

        # what a property is, when the mouse rests on its name
        self.hover = PropertyLabelHover(self)
        self.scroll_area.verticalScrollBar().valueChanged.connect(lambda _value: self.hover.hide())

        self._create_content()
        self._shows_content = True

    def set_validator(self, validator: PropertyValidator):
        self._validator = validator

    def set_session(self, session: PlateSession):
        """The draft the edited objects belong to: edits change their source (literal values or templates)."""
        self._session = session

    def set_part_focus(self, focus: Optional[PartFocus]):
        """The part mode of the editor (None outside of it): which objects can be changed depends on it."""
        self._part_focus = focus

    @property
    def _editing(self) -> Union[PlateSession, PartFocus]:
        """What changes the objects: the part mode, or the draft outside of it."""
        return self._session if self._part_focus is None else self._part_focus

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
        self._pending_directive_templates = {}

        self.refresh()
        self.scroll_area.verticalScrollBar().setValue(0)

    def _add_header(self, obj_data: Dict):
        """The name and type of the object, and the file it is defined in, above a line."""
        title_row = UiComponents.create_row(alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(UiComponents.create_label(object_name(obj_data), role="title"))
        title_row.addWidget(_badge(str(obj_data.get("obj", "?")), "The type of the object"))
        title_row.addStretch(1)
        self.main_layout.addLayout(title_row)
        self.main_layout.addLayout(self._create_file_row(obj_data))

        line = QFrame()
        line.setProperty("role", "separator")
        line.setFixedHeight(1)
        self.main_layout.addWidget(line)

    def _create_file_row(self, obj_data: Dict) -> QHBoxLayout:
        """The file the object is defined in, marked if it is a part or a shared file."""
        origin = self._session.origin_of(obj_data)
        if origin is not None:
            location = f"{relative_config_path(origin.file, self._session.device.path)}:{origin.line}"
            badge = _badge("included", "The object is written in a part, which an !include puts into the page")
        else:
            component = self._session.component_of(obj_data)
            location = relative_config_path(component.path, self._session.device.path)
            badge = None
            if component.is_common:
                badge = _badge(
                    "shared", "A file of the common folder: saving it changes the pages of every device that loads it."
                )
        # a long path wraps (at the slashes)
        row = _plain_layout(QHBoxLayout())
        icon = UiComponents.create_icon_label("file-document-outline", size=UiDimensions.two)
        row.addWidget(icon, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        label = UiComponents.create_label(location, role="hint", word_wrap=True)
        label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(label, 1)
        if badge is not None:
            row.addWidget(badge, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        return row

    def _add_notice(self, text: str, buttons: List[QWidget]):
        """A note about the object, with what can be done about it, in a box."""
        box = QFrame()
        box.setProperty("role", "notice")
        column = _plain_layout(QVBoxLayout(box))
        column.setContentsMargins(UiDimensions.one, UiDimensions.one, UiDimensions.one, UiDimensions.one)
        column.setSpacing(UiDimensions.one)
        row = _plain_layout(QHBoxLayout())
        row.setSpacing(UiDimensions.one)
        icon = UiComponents.create_icon_label("information-outline", size=UiDimensions.two)
        row.addWidget(icon, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        row.addWidget(UiComponents.create_label(text, word_wrap=True), 1)
        column.addLayout(row)
        for button in buttons:
            column.addWidget(button, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.main_layout.addWidget(box)

    def refresh(self):
        """Rebuilds the editor from the current data, e.g. after the object was moved in the preview."""
        with frozen(self.content_container):
            clear_layout(self.main_layout)
            self._create_content()
            self._shows_content = True

    def _create_content(self):
        # the labels it is about are made again
        self.hover.reset()
        self._value_updates = []
        if not self._editable_widgets:
            if self._edit_mode:
                hint = "Select an object on the plate to edit its properties."
            else:
                hint = "Turn on Edit (Ctrl+E) to select and change objects."
            self._add_hint(hint)
            return

        if len(self._editable_widgets) > 1:
            self._add_hint(f"{len(self._editable_widgets)} objects selected. Select a single object to edit its properties.")
            self._add_locked_position_hint()
            self._add_remove_button()
            return

        editable_widget = self._editable_widgets[0]
        obj_data = editable_widget.obj_data

        self._add_header(obj_data)
        if self._editing.read_only_reason(obj_data) is not None:
            # in part mode the objects of the part can be changed like the others
            self._add_included_content(obj_data)
            return
        if self._session.is_part_alone:
            # the vars the part is shown with, which only the panel has
            self._add_instance_group(obj_data)
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
        """
        An included object can't be changed: why, where to change it, the `vars` and `for` of its `!include` (which can be
        changed), and its properties (read-only).
        """
        origin = self._session.origin_of(obj_data)
        directive_file = self._session.component_of(obj_data).path
        self._add_notice(
            self._editing.read_only_reason(obj_data),
            [
                UiComponents.create_button(
                    title="Edit the part",
                    icon="puzzle-edit-outline",
                    tooltip="Edit the objects of the part on the page, in this instance: every instance follows",
                    on_click=lambda: self.editPartRequested.emit(obj_data),
                ),
                UiComponents.create_button(
                    title="Open the part",
                    icon="file-document-edit-outline",
                    tooltip="Show the object in the file it is written in, where every instance of the part changes with it",
                    on_click=lambda: self.openSourceRequested.emit(origin.file, origin.line),
                ),
                UiComponents.create_button(
                    title="Go to the !include",
                    icon="file-code-outline",
                    tooltip="Show the directive that includes the part, with its vars",
                    on_click=lambda: self.openSourceRequested.emit(directive_file, self._session.line_of(obj_data)),
                ),
            ],
        )
        if self._part_focus is None:
            # in part mode an object of a part inside of the part: its !include is written in the part
            self._add_instance_group(obj_data)
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
                # a change of the vars renders the object again
                self._value_updates.append(lambda value=value, key=key: value.setText(str(obj_data.get(key, ""))))
                form_layout.addRow(UiComponents.create_label(f"{key}:"), value)
            self.main_layout.addWidget(group)

    def _add_instance_group(self, obj_data: Dict):
        """
        The `vars` and `for` of the `!include` in the file of the draft that includes the object, as fields, and the
        `!include`s inside of parts on the way to it (read-only: they are written in the parts).
        """
        origin = self._session.origin_of(obj_data)
        component = self._session.component_of(obj_data)
        directive = self._session.directive_of(obj_data)
        group = QGroupBox("Instance")
        column = _plain_layout(QVBoxLayout(group))
        column.setContentsMargins(UiDimensions.one, UiDimensions.one, UiDimensions.one, UiDimensions.one)
        column.setSpacing(UiDimensions.one)

        if component.is_scratch:
            title = "The part is shown on its own, with these vars. They are not saved: only the part is."
        else:
            where = f"{relative_config_path(component.path, self._session.device.path)}:{self._session.line_of(obj_data)}"
            title = f"The {INCLUDE} at {where}"
        row = _plain_layout(QHBoxLayout())
        row.addWidget(UiComponents.create_label(title, role="hint", word_wrap=True), 1)
        if component.is_common:
            row.addWidget(
                _badge("shared", "A file of the common folder: changing the !include changes every device that loads it."),
                0,
                QtCore.Qt.AlignmentFlag.AlignTop,
            )
        column.addLayout(row)
        if component.is_common:
            column.addWidget(
                UiComponents.create_label(
                    f"The {INCLUDE} is in a shared file: saving a change changes the pages of every device that loads it.",
                    role="hint",
                    word_wrap=True,
                )
            )

        for key, title, empty in [
            (VARS, "vars", "No vars: the part has the variables of the file."),
            (FOR, "for", "No for: the part is included once."),
        ]:
            column.addWidget(UiComponents.create_label(title, role="section"))
            # what is wrong with adding or removing a name of the section
            error_label = UiComponents.create_label("", role="error", word_wrap=True)
            error_label.setObjectName(f"{key}-error")
            error_label.hide()
            values = directive.get(key, {})
            if not values:
                column.addWidget(UiComponents.create_label(empty, role="hint", word_wrap=True))
            else:
                form = QFormLayout()
                form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
                form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
                # a var that is a mapping (e.g. `progress_bar: {id: 30, text: ...}`) has a field for each of its values
                for name in _leaf_names(values) if key == VARS else values:
                    form.addRow(
                        self._create_directive_label(obj_data, key, name, error_label),
                        self._create_directive_field(obj_data, key, name),
                    )
                column.addLayout(form)
            column.addLayout(self._create_directive_add_row(obj_data, key, error_label))
            column.addWidget(error_label)

        for step in origin.includes[1:]:
            column.addLayout(self._create_nested_include_row(step))
        self.main_layout.addWidget(group)

    def _create_nested_include_row(self, step: IncludeStep) -> QVBoxLayout:
        """An `!include` inside of a part: where it is, its values for this instance, and a button to go to it."""
        layout = _plain_layout(QVBoxLayout())
        where = f"{relative_config_path(step.file, self._session.device.path)}:{step.line}"
        values = ", ".join(f"{name}={value!r}" for name, value in {**step.vars, **step.loop}.items())
        text = f"Inside of the part, the {INCLUDE} at {where}" + (f" ({values})" if values else "")
        layout.addWidget(UiComponents.create_label(text, role="hint", word_wrap=True))
        layout.addWidget(
            UiComponents.create_button(
                title="Go to the !include",
                icon="file-code-outline",
                tooltip="It is written in a part: change it there",
                on_click=lambda: self.openSourceRequested.emit(step.file, step.line),
            ),
            0,
            QtCore.Qt.AlignmentFlag.AlignLeft,
        )
        return layout

    def _create_directive_label(self, obj_data: Dict, key: str, name: str, error_label: QLabel) -> QWidget:
        """The name of a value of `vars` or `for`, with a button that removes it from the `!include`."""
        container = QWidget()
        row = UiComponents.create_row(container, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        row.setSpacing(UiDimensions.half)
        remove = UiComponents.create_button(
            title="",
            icon="close",
            tooltip=f"Remove {name} from {key}",
            variant="flat",
            on_click=lambda: self._remove_directive_name(obj_data, key, name, error_label),
        )
        remove.setObjectName(f"remove {key}.{name}")
        remove.setFixedSize(UiDimensions.three, UiDimensions.three)
        row.addWidget(remove)
        row.addWidget(UiComponents.create_label(f"{name}:"))
        return container

    def _create_directive_add_row(self, obj_data: Dict, key: str, error_label: QLabel) -> QHBoxLayout:
        """A name and a value to add to `vars` or `for` of the `!include` (with Enter or the button)."""
        row = _plain_layout(QHBoxLayout())
        name_editor = UiComponents.create_edittext()
        name_editor.setObjectName(f"{key} new name")
        name_editor.setPlaceholderText("name")
        name_editor.setToolTip(
            "A new variable of the part" if key == VARS else "A new loop variable: the part is included once for each value"
        )
        value_editor = UiComponents.create_edittext()
        value_editor.setObjectName(f"{key} new value")
        value_editor.setPlaceholderText("value" if key == VARS else "[1, 2, 3]")
        value_editor.setToolTip(
            "A text, a JSON value (a number, a list, ...) or a template"
            if key == VARS
            else "The values of the loop variable: a JSON list or a template"
        )
        add = QToolButton()
        add.setAutoRaise(True)
        ThemedIcons.apply(add, "plus")
        add.setToolTip(f"Add the name to {key}")
        add.setObjectName(f"add {key}")

        def apply():
            self._add_directive_name(obj_data, key, name_editor.text().strip(), value_editor.text(), error_label)

        name_editor.returnPressed.connect(apply)
        value_editor.returnPressed.connect(apply)
        add.clicked.connect(apply)
        row.addWidget(name_editor, 1)
        row.addWidget(value_editor, 2)
        row.addWidget(add)
        return row

    def _add_directive_name(self, obj_data: Dict, key: str, name: str, text: str, error_label: QLabel):
        directive = self._session.directive_of(obj_data)
        error = _directive_name_error(name, directive)
        value = None
        if error is None:
            value, error = _parse_new_directive_value(text, key)
        if error is None:
            mapping = {**directive.get(key, {}), name: value}
            error = self._session.check_directive_value(obj_data, key, mapping)
        error_label.setText(error or "")
        error_label.setVisible(error is not None)
        if error is not None:
            return
        # the panel is made again for the new field
        with self._session.edit(f"Add {key}.{name} to the {INCLUDE}"):
            self._session.set_directive_value(obj_data, key, mapping)
        # go on with its value
        added = self.findChild(QLineEdit, f"{key}.{name}")
        if added is not None:
            added.setFocus()

    def _remove_directive_name(self, obj_data: Dict, key: str, name: str, error_label: QLabel):
        """Remove a name of `vars` or `for`: the last one removes the key from the `!include`."""
        mapping = _without_value_at(self._session.directive_of(obj_data)[key], name)
        error = self._session.check_directive_value(obj_data, key, mapping)
        error_label.setText(error or "")
        error_label.setVisible(error is not None)
        if error is not None:
            return
        for pending in [pending for pending in self._pending_directive_templates if pending[0] == key]:
            if pending[1] == name or pending[1].startswith(f"{name}."):
                self._pending_directive_templates.pop(pending)
        # the panel is made again without the field
        with self._session.edit(f"Remove {key}.{name} from the {INCLUDE}"):
            self._session.set_directive_value(obj_data, key, mapping)

    def _create_directive_field(self, obj_data: Dict, key: str, name: str) -> QWidget:
        """
        The editor of a value of `vars` or `for` of an `!include`: a literal value (JSON, or a text for a var that is a text)
        or a template, switched by the button next to it. The values of this instance are shown below it.
        :param name: the name of the variable, with dots for a value inside of a mapping (`progress_bar.id`)
        """
        value = _value_at(self._session.directive_of(obj_data)[key], name)
        is_template = _is_template(value)
        template_mode = is_template or (key, name) in self._pending_directive_templates
        step = self._session.origin_of(obj_data).includes[0]
        # a var whose value is a text is edited as a text, everything else as JSON
        as_text = key == VARS and isinstance(_value_at(step.vars, name), str)

        container = QWidget()
        row = _plain_layout(QHBoxLayout(container))
        column = _plain_layout(QVBoxLayout())
        row.addLayout(column, 1)
        if template_mode:
            text = value if is_template else self._pending_directive_templates[(key, name)]
        else:
            text = value if as_text else json.dumps(value, ensure_ascii=False)
        editor = UiComponents.create_edittext(text=text)
        editor.setObjectName(f"{key}.{name}")
        if template_mode:
            editor.setPlaceholderText("{{ variable }}")
            editor.setToolTip(
                "A Jinja template, rendered with the variables of the file of the !include"
                + (" and the for variables" if key == VARS else "")
            )
            suggestions = self._session.template_suggestions(obj_data)
            if key == VARS:
                suggestions = [(f"{{{{ {loop} }}}}", loop_value) for loop, loop_value in step.loop.items()] + suggestions
            TemplateCompleter(editor, suggestions)
        elif key == FOR:
            editor.setToolTip("The values of the loop variable, a JSON list: the part is included once for each")
        else:
            editor.setToolTip("The value of the variable: a text, or a JSON value (a number, a list, ...)")
        # the start of a long template is what tells it apart
        editor.setCursorPosition(0)
        column.addWidget(editor)

        value_label = UiComponents.create_label("", role="hint", word_wrap=True)
        error_label = UiComponents.create_label("", role="error", word_wrap=True)
        column.addWidget(value_label)
        column.addWidget(error_label)
        error_label.hide()

        def show_value():
            if not any(widget.obj_data is obj_data for widget in self._editable_widgets):
                # the edit removed the object (e.g. its loop value), the panel shows another selection
                return
            current = self._session.origin_of(obj_data).includes[0]
            if key == FOR:
                value_label.setText(f"This instance: {current.loop[name]!r}")
            else:
                value_label.setText(f"= {_value_at(current.vars, name)!r}")
            value_label.setVisible(key == FOR or _is_template(_value_at(self._session.directive_of(obj_data)[key], name)))

        def apply(new_text: str):
            new_value, error = _parse_directive_value(new_text, key, as_text, template_mode)
            mapping = self._session.directive_of(obj_data)[key]
            if error is None:
                mapping = _with_value_at(mapping, name, new_value)
                if mapping != self._session.directive_of(obj_data)[key]:
                    error = self._session.check_directive_value(obj_data, key, mapping)
            error_label.setText(error or "")
            error_label.setVisible(error is not None)
            if template_mode and error is not None:
                # the panel is made again e.g. after an undo: keep what was typed
                self._pending_directive_templates[(key, name)] = new_text
            if error is not None or mapping == self._session.directive_of(obj_data)[key]:
                return
            self._pending_directive_templates.pop((key, name), None)
            self._directive_focus = (obj_data, key, name, editor.cursorPosition())
            # typing into the field is one step
            typing = ("directive", self._session.component_of(obj_data).key, self._session.source_index(obj_data), key, name)
            try:
                with self._edit(f"Change {key}.{name} of the {INCLUDE}", merge_key=typing):
                    self._session.set_directive_value(obj_data, key, mapping)
            finally:
                self._directive_focus = None
            show_value()

        show_value()
        self._value_updates.append(show_value)
        focus = self._directive_focus
        if focus is not None and focus[0] is obj_data and focus[1:3] == (key, name):
            # the edit made the panel again (it added or removed objects): go on typing
            self._directive_focus = None
            editor.setFocus()
            editor.setCursorPosition(focus[3])
        elif template_mode and not is_template and editor.text() == _EMPTY_TEMPLATE:
            # just switched to a template: type the expression right away
            editor.setCursorPosition(len("{{ "))
            QtCore.QTimer.singleShot(0, editor.setFocus)
        elif template_mode and not is_template:
            apply(editor.text())
        editor.textChanged.connect(apply)

        toggle = QToolButton()
        toggle.setCheckable(True)
        toggle.setChecked(template_mode)
        toggle.setAutoRaise(True)
        ThemedIcons.apply(toggle, "code-braces")
        toggle.setToolTip("Use a template (Jinja, with the variables of the file of the !include) instead of a value")
        toggle.toggled.connect(lambda checked: self._set_directive_template_mode(obj_data, key, name, checked))
        row.addWidget(toggle, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        return container

    def _set_directive_template_mode(self, obj_data: Dict, key: str, name: str, enabled: bool):
        if enabled:
            self._pending_directive_templates[(key, name)] = _EMPTY_TEMPLATE
        else:
            self._pending_directive_templates.pop((key, name), None)
            if _is_template(_value_at(self._session.directive_of(obj_data)[key], name)):
                # keep the values of this instance, as literals
                mapping = _with_value_at(
                    self._session.directive_of(obj_data)[key], name, self._instance_values(obj_data, key, name)
                )
                error = self._session.check_directive_value(obj_data, key, mapping)
                if error is None:
                    with self._edit(f"Change {key}.{name} of the {INCLUDE}"):
                        self._session.set_directive_value(obj_data, key, mapping)
        self.refresh()

    def _instance_values(self, obj_data: Dict, key: str, name: str) -> Any:
        """
        :return: the value of a var of the instance of the object, or for a loop variable the values of all instances of the
            `!include` (each once, in their order)
        """
        step = self._session.origin_of(obj_data).includes[0]
        if key == VARS:
            return _value_at(step.vars, name)
        values = []
        for objects in self._session.working_objects.values():
            for other in objects:
                origin = self._session.origin_of(other)
                if (
                    origin is not None
                    and self._session.component_of(other).key == self._session.component_of(obj_data).key
                    and self._session.source_index(other) == self._session.source_index(obj_data)
                    and origin.includes[0].loop[name] not in values
                ):
                    values.append(origin.includes[0].loop[name])
        return values

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
        issues = []
        if key not in source:
            label.setProperty("role", "hint")
            issues.append(
                (Severity.HINT, "Not in the file: a default of the theme or computed. Changing it writes it to the file.")
            )
        obj_type = obj_data.get("obj")
        self.hover.watch(label, lambda: CardContent(issues, property_help(key, obj_type)))
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
        self._add_notice(
            text,
            [
                UiComponents.create_button(
                    title="Use pixels for x/y",
                    icon="lock-open-variant-outline",
                    tooltip="Replace the templates and percentages in x and y with the pixels they show now, "
                    "so the object can be moved.\nOther objects that use the same variables don't follow it anymore.",
                    on_click=self.usePixelPositionClicked.emit,
                )
            ],
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
            self._editing.set_source_value(widget.obj_data, key, copy.deepcopy(self._original_snapshot[key]))
        else:
            self._editing.remove_source_value(widget.obj_data, key)

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
        """
        Show the values after the draft changed. If this panel changed it, only the values that its edit changes are updated:
        making the panel again would interrupt typing.
        """
        if not self._applying:
            self.refresh()
            return
        for update in self._value_updates:
            update()

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
            # the source changes once a valid template was entered. It starts with the braces, the cursor between them: a template
            # needs them anyway, and text before or after them or more of them can still be typed (`{{ x }}px`, `p{{ a }}b{{ b }}`)
            self._pending_templates[key] = _EMPTY_TEMPLATE
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
                error = self._session.check_template(obj_data, text) or self._editing.check_value(obj_data, key, text)
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
        if editor.text() == _EMPTY_TEMPLATE and not is_template:
            # just switched to a template: nothing to check yet, type the expression right away
            editor.setCursorPosition(len("{{ "))
            QtCore.QTimer.singleShot(0, editor.setFocus)
        elif editor.text() and not is_template:
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

        if choices := value_choices(obj_data.get("obj"), key):
            editor = self._create_choice_editor(choices, value, apply)
            row.addWidget(editor, 1)
        elif isinstance(value, bool):
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

    @staticmethod
    def _create_choice_editor(choices, value: Any, apply: Callable[[Any], None]) -> QComboBox:
        """A list of the values a property takes, with what each means. A value that is none of them stays, marked as such."""
        editor = QComboBox()
        for choice in choices:
            editor.addItem(f"{_shown(choice.value)} \N{EM DASH} {choice.meaning}", choice.value)
        current = matching_choice(choices, value)
        if current is None:
            editor.insertItem(0, f"{_shown(value)} \N{EM DASH} not a value the plate takes", value)
            editor.setCurrentIndex(0)
        else:
            editor.setCurrentIndex(choices.index(current))
        editor.setToolTip("The values this property takes")
        # the meanings are long: they would make the panel too wide for its dock. The closed list shows what fits, the open one all
        editor.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        editor.setMinimumContentsLength(_CHOICE_MIN_CHARACTERS)
        texts = [editor.itemText(index) for index in range(editor.count())]
        editor.view().setMinimumWidth(
            max(editor.fontMetrics().horizontalAdvance(text) for text in texts) + UiDimensions.four
        )
        editor.currentIndexChanged.connect(lambda index: apply(editor.itemData(index)))
        return editor

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
        return self._editing.check_value(obj_data, key, value)

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
            self._editing.set_source_value(widget.obj_data, key, value)


# how many characters of a value list the closed dropdown needs room for, e.g. "scroll — keep"
_CHOICE_MIN_CHARACTERS = 12

# what the field of a property starts with when it is switched to a template
_EMPTY_TEMPLATE = "{{  }}"


def _is_template(value: Any) -> bool:
    return isinstance(value, str) and ("{{" in value or "{%" in value)


def _leaf_names(variables: Dict[str, Any], prefix: str = "") -> List[str]:
    """:return: the names of the values of `vars`, with dots for those inside of mappings (`progress_bar.id`)"""
    result = []
    for name, value in variables.items():
        if isinstance(value, dict) and value:
            result += _leaf_names(value, f"{prefix}{name}.")
        else:
            result.append(f"{prefix}{name}")
    return result


def _value_at(variables: Dict[str, Any], name: str) -> Any:
    """:return: the value of a name of `_leaf_names`"""
    value: Any = variables
    for part in name.split("."):
        value = value[part]
    return value


def _with_value_at(variables: Dict[str, Any], name: str, value: Any) -> Dict[str, Any]:
    """:return: a copy of the variables with another value for a name of `_leaf_names`, in the same order"""
    first, _dot, rest = name.partition(".")
    return {**variables, first: _with_value_at(variables[first], rest, value) if rest else value}


def _without_value_at(variables: Dict[str, Any], name: str) -> Dict[str, Any]:
    """:return: a copy of the variables without a name of `_leaf_names`, and without the mappings that are empty then"""
    first, _dot, rest = name.partition(".")
    result = dict(variables)
    if rest:
        result[first] = _without_value_at(variables[first], rest)
        if result[first]:
            return result
    result.pop(first)
    return result


# names that the templates of objects use for objects (`this`, `b4`): a variable with such a name is hidden there
_OBJECT_NAME = re.compile(r"this|b\d+")


def _directive_name_error(name: str, directive: Dict[str, Any]) -> Optional[str]:
    """:return: why a name can't be added to `vars` or `for` of the `!include`, None if it can"""
    if not name:
        return "Enter a name."
    if not name.isidentifier() or keyword.iskeyword(name):
        return f"{name} is not a name that templates can use: letters, digits and _, not starting with a digit."
    if _OBJECT_NAME.fullmatch(name):
        return f"{name} is the name of an object in the templates."
    for key in INCLUDE_KEYS:
        if name in directive.get(key, {}):
            return f"{name} is already in {key}."
    return None


def _parse_new_directive_value(text: str, key: str) -> Tuple[Any, Optional[str]]:
    """
    :return: the value of a new name of `vars` or `for` as it is written in the `!include` (a template, JSON, or for a var
        a text if it is no JSON), or why it is none
    """
    if _is_template(text):
        return text, None
    if key == VARS:
        try:
            return json.loads(text), None
        except ValueError:
            return text, None
    return _parse_directive_value(text, key, as_text=False, template=False)


def _parse_directive_value(text: str, key: str, as_text: bool, template: bool) -> Tuple[Any, Optional[str]]:
    """
    :param as_text: the value is a text (a var whose value is a text), not JSON
    :param template: the text is a template
    :return: the value of a field of `vars` or `for` as it is written in the `!include`, or why it is none
    """
    if template:
        if not _is_template(text):
            return None, "Enter a template, e.g. {{ variable }}."
        return text, None
    if as_text:
        if _is_template(text):
            return None, "This is a template: switch to template mode with the { } button."
        return text, None
    try:
        value = json.loads(text)
    except ValueError:
        if key == FOR:
            return None, "Write a JSON list of values, e.g. [1, 2, 3], or use a template."
        return None, 'Write a JSON value, e.g. 12, "a text" or [1, 2], or use a template.'
    if key == FOR and not isinstance(value, list):
        return None, "Write a JSON list of values, e.g. [1, 2, 3], or use a template."
    return value, None


def _badge(text: str, tooltip: str) -> QLabel:
    """A small framed word next to a name, e.g. the type of an object."""
    badge = UiComponents.create_label(text, role="badge")
    badge.setToolTip(tooltip)
    badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return badge


def _shown(value: Any) -> str:
    """A value the way it is written in a file: `true`, `1`, `dots`."""
    return str(value).lower() if isinstance(value, bool) else str(value)


def _plain_layout[L: QHBoxLayout | QVBoxLayout](layout: L) -> L:
    """
    A layout without margins and without an alignment of its own: an alignment keeps word-wrapped labels in it
    (e.g. errors) from growing in height.
    """
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(UiDimensions.half)
    return layout
