"""
The preview against screenshots of a real plate (an openHASP device showing the objects of `cases.json` on page 6). It guards what was
fitted to the device: a change that makes an object differ more from the screenshot than it did when `baseline.json` was written fails.

After a change that makes the preview better (or an intended change), write the baseline again with `UPDATE_PREVIEW_BASELINE=1`.
The screenshots show the font Roboto Condensed, which is part of the resources, so the result doesn't depend on the installed fonts.
"""

import io
import json
import os
from pathlib import Path

import pytest
from PIL import Image, ImageChops

RESOURCES = Path(__file__).parent.parent / "resources" / "preview_device"
IMAGE_FILE = RESOURCES / "image_50x50.png"
CASES = json.loads((RESOURCES / "cases.json").read_text())
BASELINE_FILE = RESOURCES / "baseline.json"
UPDATE_BASELINE = bool(os.environ.get("UPDATE_PREVIEW_BASELINE"))

SCREEN = (480, 320)
# the navigation buttons of the plate are at the bottom of every screenshot, the preview doesn't draw them
NAVIGATION_TOP = 280
# the area around an object that is compared
MARGIN = 14
# a pixel differs if its channels differ by more than this in total
PIXEL_THRESHOLD = 60
# how much more of an object may differ than in the baseline (a share of the area, and a factor, for the noise of the font rendering)
TOLERANCE_SHARE = 0.01
TOLERANCE_FACTOR = 1.1
# objects that change by themselves
ANIMATED = ("spinner",)


@pytest.fixture(scope="module")
def plate_fonts(qapp):
    from PyQt6 import QtGui

    for font_file in (RESOURCES / "fonts").glob("*.ttf"):
        assert QtGui.QFontDatabase.addApplicationFont(str(font_file)) >= 0, font_file


def render(objects: list) -> Image.Image:
    """:return: the preview of the objects on page 6, like the screenshots show them"""
    from PyQt6 import QtCore, QtGui

    from openhasp_config_manager.gui.qt.widgets.pagelayout.page_preview_layout import PagePreviewWidget

    view = PagePreviewWidget()
    view.set_image_files({"common_page_wz_image_50x50.png": IMAGE_FILE})
    view.set_objects([{"page": 6, "id": index, **obj} for index, obj in enumerate(objects, start=1)])
    image = QtGui.QImage(*SCREEN, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtGui.QColor("black"))
    painter = QtGui.QPainter(image)
    painter.setRenderHints(
        QtGui.QPainter.RenderHint.Antialiasing
        | QtGui.QPainter.RenderHint.SmoothPixmapTransform
        | QtGui.QPainter.RenderHint.TextAntialiasing
    )
    view.scene().render(painter, QtCore.QRectF(0, 0, *SCREEN), QtCore.QRectF(0, 0, *SCREEN))
    painter.end()
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGB")


def differing_share(device: Image.Image, preview: Image.Image, box: tuple) -> float:
    """:return: the share of the pixels in the box that are different in the two images"""
    difference = ImageChops.difference(device.crop(box), preview.crop(box))
    red, green, blue = difference.split()
    histogram = ImageChops.add(ImageChops.add(red, green), blue).histogram()
    return sum(histogram[PIXEL_THRESHOLD + 1 :]) / ((box[2] - box[0]) * (box[3] - box[1]))


def compared_box(obj: dict):
    """:return: the area of the screen to compare for an object, None if the object isn't compared"""
    x, y, w, h = obj.get("x", 0), obj.get("y", 0), obj.get("w", 100), obj.get("h", 50)
    if obj["obj"] in ANIMATED or y + h > NAVIGATION_TOP:
        return None
    return max(x - MARGIN, 0), max(y - MARGIN, 0), min(x + w + MARGIN, SCREEN[0]), min(y + h + MARGIN, SCREEN[1])


def baseline() -> dict:
    return {} if UPDATE_BASELINE else json.loads(BASELINE_FILE.read_text())


@pytest.fixture(scope="module")
def measured():
    """What every case differs from its screenshot, collected to be written as the new baseline."""
    result = {}
    yield result
    if UPDATE_BASELINE:
        BASELINE_FILE.write_text(json.dumps(result, indent=1) + "\n")


@pytest.mark.usefixtures("qapp", "plate_fonts")
@pytest.mark.parametrize("name", CASES)
def test_the_preview_is_as_close_to_the_plate_as_it_was(name, measured):
    pytest.importorskip("segno")
    objects = CASES[name]
    device = Image.open(RESOURCES / "screenshots" / f"{name}.png").convert("RGB").crop((0, 0, *SCREEN))
    preview = render(objects)

    shares = []
    for obj in objects:
        box = compared_box(obj)
        shares.append(None if box is None else round(differing_share(device, preview, box), 4))
    measured[name] = shares

    if UPDATE_BASELINE:
        return
    worse = [
        f"{name}[{index}] {obj['obj']}: {share:.3f}, was {before:.3f}"
        for index, (obj, share, before) in enumerate(zip(objects, shares, baseline()[name]))
        if share is not None and share > before * TOLERANCE_FACTOR + TOLERANCE_SHARE
    ]
    assert not worse, "\n".join(worse)
