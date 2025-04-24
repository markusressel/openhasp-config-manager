import pathlib
from pathlib import Path

from PyQt6.QtWidgets import QTreeWidget, QAbstractItemView, QTreeWidgetItem

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

        self.itemClicked.connect(self.on_item_clicked)

    def clear_entries(self):
        clear_layout(self.layout)

    def create_entries(self):
        self._load_file_structure(self.cfg_root, self)

    def _load_file_structure(self, startpath: Path, tree: QTreeWidget):
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
                self._load_file_structure(path_info, parent_itm)
                parent_itm.setIcon(0, QIcon('assets/folder.ico'))
            else:
                parent_itm.setIcon(0, QIcon('assets/file.ico'))

    def on_item_clicked(self, it: QTreeWidgetItem, col: int):
        print(it, col, it.text(col))
