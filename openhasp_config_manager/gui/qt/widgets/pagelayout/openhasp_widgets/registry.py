"""The preview items of the openHASP object types that only need `(obj_data, parent_widget)`, by their `obj` value."""

from typing import Dict, Type

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.checkbox import HaspCheckboxItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.arc import HaspArcItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.dropdown import HaspDropdownItem

ITEM_CLASSES: Dict[str, Type[EditableWidget]] = {
    "checkbox": HaspCheckboxItem,
    "arc": HaspArcItem,
    "dropdown": HaspDropdownItem,
}
