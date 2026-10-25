"""The preview items of the openHASP object types that only need `(obj_data, parent_widget)`, by their `obj` value."""

from typing import Dict, Type

from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.checkbox import HaspCheckboxItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.editable_widget import EditableWidget
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.arc import HaspArcItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.dropdown import HaspDropdownItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.roller import HaspRollerItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.led import HaspLedItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.spinner import HaspSpinnerItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.linemeter import HaspLineMeterItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.gauge import HaspGaugeItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.line import HaspLineItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.qrcode import HaspQrCodeItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.base_object import HaspBaseObjectItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.tabview import HaspTabviewItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.tab import HaspTabItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.btnmatrix import HaspButtonMatrixItem
from openhasp_config_manager.gui.qt.widgets.pagelayout.openhasp_widgets.msgbox import HaspMessageBoxItem

ITEM_CLASSES: Dict[str, Type[EditableWidget]] = {
    "checkbox": HaspCheckboxItem,
    "arc": HaspArcItem,
    "dropdown": HaspDropdownItem,
    "roller": HaspRollerItem,
    "led": HaspLedItem,
    "spinner": HaspSpinnerItem,
    "linemeter": HaspLineMeterItem,
    "gauge": HaspGaugeItem,
    "line": HaspLineItem,
    "qrcode": HaspQrCodeItem,
    "obj": HaspBaseObjectItem,
    "tabview": HaspTabviewItem,
    "tab": HaspTabItem,
    "btnmatrix": HaspButtonMatrixItem,
    "msgbox": HaspMessageBoxItem,
}
