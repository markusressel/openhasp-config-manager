import re
import socket

import pytest_asyncio

from openhasp_config_manager.haad.objects import image
from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.openhasp_client.image_server import ImageServer
from tests.haad.conftest import CFG_ROOT
from tests.haad.fakes import FakePlate

IMAGE = CFG_ROOT / "devices" / "test_device" / "home" / "image_50x50.png"


@pytest_asyncio.fixture(autouse=True)
async def _image_server(monkeypatch):
    """
    The image server is a module-level singleton, started on first use and bound to that event loop: every test gets
    its own, like every haad process.
    """
    server = ImageServer(listen_host="0.0.0.0", listen_port=image.OPENHASP_IMAGE_PORT)
    monkeypatch.setattr(image, "_global_image_server", server)
    yield
    await server.stop()


async def test_image_init_sends_nothing(page: PageController, plate: FakePlate):
    img = await page.add_image(obj_id=45)

    await img.init()

    assert plate.commands == []


async def test_push_image_serves_the_image_to_the_plate(page: PageController, plate: FakePlate, monkeypatch):
    monkeypatch.setattr(image, "OPENHASP_IMAGE_HOST", "127.0.0.1")
    img = await page.add_image(obj_id=45)

    await img.push_image(image=str(IMAGE), width=20, height=10)
    await plate.settle()

    # the second push reuses the running image server
    await img.push_image(image=str(IMAGE), width=50, height=50)
    await plate.settle()

    assert len(plate.commands) == 2
    for command in plate.commands:
        assert re.fullmatch(r"p1b45\.src=http://127\.0\.0\.1:\d+/[0-9a-f-]{36}", command), plate.commands
    # RGB565 with a 4 byte header; the 50x50 image is fit into 20x10, keeping its aspect ratio
    assert [len(data) for data in plate.downloaded_images] == [4 + 10 * 10 * 2, 4 + 50 * 50 * 2]


async def test_push_image_uses_the_local_ip_by_default(page: PageController, plate: FakePlate, monkeypatch):
    monkeypatch.setattr(image, "get_local_ip", lambda: "127.0.0.1")
    img = await page.add_image(obj_id=45)

    await img.push_image(image=str(IMAGE), width=10, height=10)
    await plate.settle()

    assert plate.commands[0].startswith("p1b45.src=http://127.0.0.1:")


async def test_push_image_logs_errors(page: PageController, plate: FakePlate, monkeypatch, caplog):
    monkeypatch.setattr(image, "OPENHASP_IMAGE_HOST", "127.0.0.1")
    img = await page.add_image(obj_id=45)

    await img.push_image(image="/nonexistent.png", width=10, height=10)

    assert plate.commands == []
    assert "Error pushing image" in caplog.text


def test_get_local_ip():
    assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", image.get_local_ip())


def test_get_local_ip_falls_back_to_localhost(monkeypatch):
    class _Socket:
        def __init__(self, *args):
            pass

        def connect(self, address):
            raise OSError("Network is unreachable")

        def close(self):
            pass

    monkeypatch.setattr(socket, "socket", _Socket)

    assert image.get_local_ip() == "127.0.0.1"


async def test_image_property_setters(page: PageController, plate: FakePlate):
    img = await page.add_image(obj_id=45)

    await img.set_offset(1, 2)
    await img.set_offset()
    await img.set_zoom(128)
    await img.set_zoom()
    await img.set_angle(458)
    await img.set_angle()
    await img.set_pivot(3, 4)
    await img.set_pivot()
    await img.set_antialiasing(True)
    await img.set_antialiasing()

    assert plate.commands == [
        "p1b45.offset_x=1", "p1b45.offset_y=2",
        "p1b45.offset_x=0", "p1b45.offset_y=0",
        "p1b45.zoom=128",
        "p1b45.zoom=256",
        "p1b45.angle=458",
        "p1b45.angle=0",
        "p1b45.pivot_x=3", "p1b45.pivot_y=4",
        "p1b45.pivot_x=0", "p1b45.pivot_y=0",
        "p1b45.antialias=True",
        "p1b45.antialias=False",
    ]
