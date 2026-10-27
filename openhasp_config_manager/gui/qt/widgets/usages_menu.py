from pathlib import Path
from typing import Callable, List

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMenu, QWidget

from openhasp_config_manager.gui.domain.variable_usages import Usage

_MAX_SNIPPET = 80


def _snippet(usage: Usage) -> str:
    lines = usage.path.read_text(encoding="utf-8").splitlines()
    text = lines[usage.line - 1].strip() if usage.line <= len(lines) else ""
    return text if len(text) <= _MAX_SNIPPET else text[: _MAX_SNIPPET - 1] + "…"


def show_usages_menu(
    parent: QWidget, usages: List[Usage], config_dir: Path, position: QPoint, chosen: Callable[[Usage], None]
) -> QMenu:
    """Let the user choose one of the places a variable is used, like the list of usages of an IDE."""
    menu = QMenu(parent)
    for usage in usages:
        label = f"{usage.path.relative_to(config_dir.resolve())}:{usage.line}    {_snippet(usage)}"
        menu.addAction(label.replace("&", "&&"), lambda usage=usage: chosen(usage))
    menu.popup(position)
    return menu
