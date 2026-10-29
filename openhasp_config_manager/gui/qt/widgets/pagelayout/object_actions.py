from typing import Dict, List, Optional

from jinja2 import TemplateError
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QMessageBox

from openhasp_config_manager.gui.domain.draft.clipboard import (
    PasteCascade,
    objects_from_text,
    objects_to_text,
    with_descendants,
)
from openhasp_config_manager.gui.domain.draft.page_objects import OpenHASPWidgetType, create_object, next_free_id
from openhasp_config_manager.gui.domain.problems import object_name
from openhasp_config_manager.gui.domain.tabs import last_tabview_id
from openhasp_config_manager.gui.qt.operations import error_text
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

LOCKED_POSITION_HINT = "the position is a template or a percentage: use pixels for x/y in the properties to move it"
LOCKED_POSITION_FIX = "To move it, use pixels for x/y in the properties: this replaces the template or percentage."
INCLUDED_HINT = "an !include puts it into the file: change it in the part, or the vars of the !include"


class ObjectActions(QObject):
    """What the user does with the objects of the page of a `PageLayoutEditorWidget`: add, move, copy, paste, duplicate, remove."""

    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor
        self._paste_cascade = PasteCascade()

    def is_movable(self, obj: Dict) -> bool:
        """
        Objects whose position is a template or a percentage can't be dragged: it would replace them with pixels. Included
        objects can't be changed at all.
        """
        session = self._editor.session
        return not session.is_included(obj) and not session.has_computed_position(obj)

    def report_locked(self, items: List[EditableWidget]):
        """Explain why objects can't be moved: in the status bar, and next to the first of them."""
        items = self._changeable(items, "Moving")
        if not items:
            return
        names = ", ".join(f"p{item.obj_data.get('page')}b{item.obj_id}" for item in items)
        self._editor.status.failed.emit(f"Moving {names}", LOCKED_POSITION_HINT)
        first = items[0]
        reasons = "\n".join(self._editor.session.computed_position_reasons(first.obj_data))
        name = f"p{first.obj_data.get('page')}b{first.obj_id}"
        self._editor.page_preview_widget.show_message(f"{name} can't be moved:\n{reasons}\n{LOCKED_POSITION_FIX}", near=first)

    def _changeable(self, items: List[EditableWidget], action: str) -> List[EditableWidget]:
        """:return: the objects that are not included; why the others can't be changed is shown (see `report_included`)"""
        included = [item for item in items if self._editor.session.is_included(item.obj_data)]
        if included:
            self.report_included(included, action)
        return [item for item in items if not any(item is other for other in included)]

    def report_included(self, items: List[EditableWidget], action: str):
        """Explain why included objects can't be changed: in the status bar, and next to the first of them."""
        names = ", ".join(object_name(item.obj_data) for item in items)
        self._editor.status.failed.emit(f"{action} {names}", INCLUDED_HINT)
        first = items[0]
        reason = self._editor.session.read_only_reason(first.obj_data)
        self._editor.page_preview_widget.show_message(
            f"{object_name(first.obj_data)} can't be changed here:\n{reason}", near=first
        )

    def use_pixel_positions(self):
        """Replace the templates and percentages in x and y of the selected objects with pixels, so they can be moved."""
        items = self._editor.page_preview_widget.selected_items()
        if not self._editor.edit_mode or not items:
            return
        items = self._changeable(items, "Using pixels for")
        if not items:
            return
        with self._editor.session.edit(self._describe("Use pixels for x/y of", items)):
            for item in items:
                self._editor.session.use_pixel_position(item.obj_data)

    def on_items_moved(self, items: List[EditableWidget]):
        with self._editor.session.edit(self._describe("Move", items)):
            for item in items:
                self._move(item, item.live_x, item.live_y)

    def nudge_selected(self, dx: int, dy: int):
        items = self._editor.page_preview_widget.selected_items()
        if not self._editor.edit_mode or not items:
            return
        locked = [item for item in items if not self.is_movable(item.obj_data)]
        if locked:
            self.report_locked(locked)
        movable = [item for item in items if item not in locked]
        # pressing the keys again and again is one step
        nudged = ("nudge", tuple(sorted(self._editor.session.object_uid(item.obj_data) for item in movable)))
        with self._editor.session.edit(self._describe("Move", movable), merge_key=nudged):
            for item in movable:
                self._move(item, item.obj_x + dx, item.obj_y + dy)

    def _move(self, item: EditableWidget, x: int, y: int):
        self._editor.session.set_source_value(item.obj_data, "x", x)
        self._editor.session.set_source_value(item.obj_data, "y", y)

    @staticmethod
    def _describe(action: str, items: List[EditableWidget]) -> str:
        """:return: e.g. "Move p1b2" or "Move 3 objects", for the undo history"""
        if len(items) == 1:
            return f"{action} {object_name(items[0].obj_data)}"
        return f"{action} {len(items)} objects"

    def add(self, widget_type: OpenHASPWidgetType):
        component = self._editor.target_component
        if component is None:
            return
        if not self._editor.edit_mode:
            self._editor.action_edit_mode.setChecked(True)

        parent_id = self._parent_for(widget_type)
        if widget_type == OpenHASPWidgetType.TAB and parent_id is None:
            self._editor.status.failed.emit("Adding a tab", "A tab belongs to a tabview: add a tabview to this page first")
            return
        try:
            obj_id = next_free_id(self._editor.working_objects, self._editor.current_index)
        except ValueError as ex:
            self._editor.status.failed.emit(f"Adding a {widget_type}", error_text(ex))
            return
        screen = self._editor.device_pages_data.device.config.openhasp_config_manager.device.screen
        obj = create_object(
            widget_type,
            page=self._editor.current_index,
            obj_id=obj_id,
            screen_width=screen.width,
            screen_height=screen.height,
            parent_id=parent_id,
        )
        self._editor.session.add_object(component, obj)

    def _parent_for(self, widget_type: OpenHASPWidgetType) -> Optional[int]:
        """The object a new object belongs to: a tab goes into the last tabview of the page."""
        if widget_type != OpenHASPWidgetType.TAB:
            return None
        objects = [obj for objects in self._editor.working_objects.values() for obj in objects]
        return last_tabview_id(objects, self._editor.current_index)

    def duplicate_selected(self):
        items = self._editor.page_preview_widget.selected_items()
        if not self._editor.edit_mode or not items:
            return
        # their templates need the variables of their instance
        items = self._changeable(items, "Duplicating")
        if not items:
            return
        with self._editor.session.edit(self._describe("Duplicate", items)):
            for item in items:
                try:
                    self._editor.session.duplicate_object(item.obj_data)
                except ValueError as ex:
                    self._editor.status.failed.emit(f"Duplicating p{item.obj_data.get('page')}b{item.obj_id}", error_text(ex))
                    break

    def copy_selected(self):
        """
        Copy the selected objects (with the objects inside of them) to the clipboard, as JSONL with their templates. Not the
        included ones: their templates need the variables of their instance.
        """
        items = self._editor.page_preview_widget.selected_items()
        if not self._editor.edit_mode or not items:
            return
        items = self._changeable(items, "Copying")
        if not items:
            return
        objects = with_descendants(self._editor.page_objects, [item.obj_data for item in items])
        objects = [obj for obj in objects if not self._editor.session.is_included(obj)]
        QApplication.clipboard().setText(objects_to_text([self._editor.session.source_of(obj) for obj in objects]))
        self._paste_cascade.reset()

    def paste(self):
        """
        Paste the objects of the clipboard into the file for new objects: where the mouse is, if it is over the plate,
        otherwise next to the originals. Pasting again to the same spot moves the copies a bit further each time.
        """
        component = self._editor.target_component
        if component is None:
            return
        text = QApplication.clipboard().text()
        sources = objects_from_text(text)
        if not sources:
            self._editor.status.failed.emit("Pasting", "the clipboard holds no openHASP objects (JSONL)")
            return
        if not self._editor.edit_mode:
            self._editor.action_edit_mode.setChecked(True)

        screen = self._editor.device_pages_data.device.config.openhasp_config_manager.device.screen
        position = self._editor.page_preview_widget.cursor_plate_position()
        try:
            self._editor.session.paste_objects(
                component,
                sources,
                page=self._editor.current_index,
                screen=(screen.width, screen.height),
                position=position,
                offset=self._paste_cascade.next_offset(text, position),
            )
        except (ValueError, TemplateError) as ex:
            self._editor.status.failed.emit("Pasting", error_text(ex))

    def remove_selected(self):
        items = self._editor.page_preview_widget.selected_items()
        if not self._editor.edit_mode or not items:
            return
        items = self._changeable(items, "Removing")
        if not items:
            return
        names = ", ".join(f"p{item.obj_data.get('page')}b{item.obj_id}" for item in items)
        answer = QMessageBox.question(
            self._editor,
            "Remove objects" if len(items) > 1 else "Remove object",
            f"Remove {names} from the page?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        with self._editor.session.edit(self._describe("Remove", items)):
            for item in items:
                self._editor.session.remove_object(item.obj_data)
