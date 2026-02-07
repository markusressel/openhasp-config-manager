from collections.abc import Callable

from PyQt6.QtWidgets import QPushButton


class UiComponents:

    @staticmethod
    def create_button(title: str, on_click: Callable[[], None]) -> QPushButton:
        button = QPushButton(title)
        button.setStyleSheet("padding: 10px;")
        button.clicked.connect(on_click)
        return button