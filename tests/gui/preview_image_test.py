from pathlib import Path

import pytest

from tests import TestBase
from tests.helpers import copy_test_config, load_session, write_page

JSONL = """{"page": 9, "id": 1, "obj": "obj", "x": 10, "y": 20, "w": 50, "h": 40, "bg_color": "#FF0000", "radius": 0, "border_width": 0}
{"page": 0, "id": 2, "obj": "obj", "x": 100, "y": 280, "w": 20, "h": 20, "bg_color": "#0000FF", "radius": 0, "border_width": 0}
{"page": 3, "id": 1, "obj": "obj", "x": 10, "y": 20, "w": 50, "h": 40, "bg_color": "#00FF00", "radius": 0, "border_width": 0}
"""


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    root = copy_test_config(tmp_path)
    write_page(root, JSONL)
    return root


def _color(image, x: int, y: int) -> str:
    """:return: the channel a pixel has most of (the theme shades the objects), or black"""
    color = image.pixelColor(x, y)
    channels = {"red": color.red(), "green": color.green(), "blue": color.blue()}
    name = max(channels, key=channels.get)
    return name if channels[name] > 2 * sorted(channels.values())[1] else "black" if channels[name] < 10 else "mixed"


class TestRenderPages(TestBase):
    def test_every_page_in_the_resolution_of_the_plate(self, qapp, cfg_root):
        from openhasp_config_manager.gui.qt.preview_image import render_pages

        # WHEN
        session = load_session(cfg_root)
        images = render_pages(session, session.device)

        # THEN: the objects of the page and of page 0, on the black screen
        assert sorted(images) == [3, 9]
        page = images[9]
        screen = session.device.config.openhasp_config_manager.device.screen
        assert (page.width(), page.height()) == (screen.width, screen.height) == (480, 320)
        assert _color(page, 30, 40) == "red"
        assert _color(page, 110, 290) == "blue"
        assert _color(page, 200, 200) == "black"
        assert _color(images[3], 30, 40) == "green"

    def test_chosen_pages_scaled(self, qapp, cfg_root):
        from openhasp_config_manager.gui.qt.preview_image import render_pages

        # WHEN
        session = load_session(cfg_root)
        images = render_pages(session, session.device, pages=[3], scale=2)

        # THEN
        [page] = images.values()
        assert (page.width(), page.height()) == (960, 640)
        assert _color(page, 60, 80) == "green"
