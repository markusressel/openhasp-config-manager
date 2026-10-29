"""
Images of the plate preview, for tools that can't look at the GUI (e.g. an LLM that edits the config files): the GUI writes
the page it shows next to its state file, and the `preview` command renders pages of the files on disk.
"""
from typing import Dict, Iterable, Optional

from PyQt6.QtCore import QBuffer, QIODevice, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from openhasp_config_manager.gui.domain.draft.page_objects import get_navigable_page_indices, get_page_objects
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget
from openhasp_config_manager.openhasp_client.model.device import Device


def render_plate(preview: PagePreviewWidget, scale: float = 1) -> QImage:
    """
    :param scale: the size of the image, 1 is the native resolution of the plate
    :return: the plate as the preview shows it: the objects (selected ones with their frame, dimmed ones dimmed), without
        the grid, the area around the plate and the floating bars
    """
    plate = preview.scene().sceneRect()
    image = QImage(round(plate.width() * scale), round(plate.height() * scale), QImage.Format.Format_RGB32)
    image.fill(QColor("black"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    preview.scene().render(painter, QRectF(image.rect()), plate)
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def render_pages(
    session: PlateSession, device: Device, pages: Optional[Iterable[int]] = None, scale: float = 1
) -> Dict[int, QImage]:
    """
    :param session: the draft of the device, loaded
    :param pages: the pages to render, all pages with objects by default
    :param scale: see `render_plate`
    :return: page -> the plate showing it, like the preview does in interact mode
    """
    preview = PagePreviewWidget()
    preview.set_device(device)
    objects = session.working_objects
    preview.set_group_objects(lambda: [obj for component in objects.values() for obj in component])
    result = {}
    for page in get_navigable_page_indices(objects) if pages is None else pages:
        preview.set_objects(get_page_objects(objects, index=page))
        result[page] = render_plate(preview, scale)
    preview.deleteLater()
    return result
