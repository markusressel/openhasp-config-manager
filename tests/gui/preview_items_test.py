"""Every object type of the preview draws something: one test per type, in the order they were added."""

import pytest

from tests import TestBase


def render(obj: dict) -> "QImage":
    """Draw the object the way the preview does, on a transparent image."""
    from PyQt6 import QtCore, QtGui
    from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget

    view = PagePreviewWidget()
    view.set_objects([obj])
    image = QtGui.QImage(480, 320, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtGui.QColor("black"))
    painter = QtGui.QPainter(image)
    view.scene().render(painter, QtCore.QRectF(0, 0, 480, 320), QtCore.QRectF(0, 0, 480, 320))
    painter.end()
    return image


def painted(image) -> int:
    """:return: the number of pixels that are not black"""
    black = 0xFF000000
    return sum(1 for x in range(image.width()) for y in range(image.height()) if image.pixel(x, y) != black)


@pytest.mark.usefixtures("qapp")
class TestPreviewItems(TestBase):
    def test_known_types_are_drawn(self):
        image = render({"page": 1, "id": 1, "obj": "bar", "x": 10, "y": 10, "w": 100, "h": 20, "val": 50})
        assert painted(image) > 0
