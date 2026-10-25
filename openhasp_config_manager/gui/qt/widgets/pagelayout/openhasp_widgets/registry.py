"""The preview items of the openHASP object types that only need `(obj_data, parent_widget)`, by their `obj` value."""

from typing import Dict, Type

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget

ITEM_CLASSES: Dict[str, Type[EditableWidget]] = {}
