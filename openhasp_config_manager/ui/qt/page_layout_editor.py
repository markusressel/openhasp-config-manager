from PyQt6.QtWidgets import QWidget, QVBoxLayout

from openhasp_config_manager.ui.qt.util import clear_layout


class PageLayoutEditorWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.create_layout()

    def create_layout(self):
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

    def clear_entries(self):
        clear_layout(self.layout)

    def set_page(self, page):
        self.clear_entries()
        self.page = page
        self._create_page_content_widgets()

    def _create_page_content_widgets(self):
        for object in self.page.objects:
            if object["type"] == "button":
                self._create_button_widget(object)

    def _create_button_widget(self, object):
        pass
