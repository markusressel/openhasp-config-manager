import pathlib
from pathlib import Path
from typing import List

from PyQt6.QtWidgets import QTreeWidget, QAbstractItemView

from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.ui.qt.util import clear_layout


class FileBrowserWidget(QTreeWidget):
    def __init__(self, cfg_root: Path):
        super().__init__()
        self.cfg_root = cfg_root
        self.create_layout()
        self.create_entries()

    def create_layout(self):
        self.setHeaderLabel("File Browser")
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setAnimated(False)
        self.setAllColumnsShowFocus(True)

    def set_devices(self, devices: List[Device]):
        self.devices = devices
        self.clear_entries()
        self.create_entries()

    def clear_entries(self):
        clear_layout(self.layout)

    def create_entries(self):
        def load_project_structure(startpath: Path, tree: QTreeWidget):
            """
            Load Project structure tree
            :param startpath:
            :param tree:
            :return:
            """
            import os
            from PyQt6.QtWidgets import QTreeWidgetItem
            from PyQt6.QtGui import QIcon
            startpath.is_dir()
            for element in sorted(pathlib.Path(startpath).iterdir(), key=lambda x: (not x.is_dir(), x.name)):
                path_info = Path(startpath, element)
                parent_itm = QTreeWidgetItem(tree, [os.path.basename(element)])
                if os.path.isdir(path_info):
                    load_project_structure(path_info, parent_itm)
                    parent_itm.setIcon(0, QIcon('assets/folder.ico'))
                else:
                    parent_itm.setIcon(0, QIcon('assets/file.ico'))

        load_project_structure(self.cfg_root, self)

    def on_device_label_clicked(self, device):
        print(f"Clicked on device: {device.name}")
