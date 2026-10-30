import asyncio
import re
import socket

import pytest
import pytest_asyncio

from openhasp_config_manager.haad.objects import image
from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.openhasp_client.image_server import ImageServer
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from tests.haad.conftest import CFG_ROOT
from tests.haad.fakes import FakePlate

PLACEHOLDER = "L:/common_page_md_empty.bin"
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


@pytest.fixture(autouse=True)
def _plate_source(monkeypatch):
    """What the plate answers when asked for the `src` of an object (its configured placeholder), and for its size."""
    reads = []

    async def get_object_property(self, obj, prop, timeout=1.0):
        reads.append((obj, prop))
        return {"w": 20, "h": 10}.get(prop, PLACEHOLDER)

    monkeypatch.setattr(OpenHaspClient, "get_object_property", get_object_property)
    return reads


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
    # RGB565 with a 4 byte header; the 50x50 image covers 20x10: the plate would repeat a smaller one
    assert [len(data) for data in plate.downloaded_images] == [4 + 20 * 10 * 2, 4 + 50 * 50 * 2]


async def test_push_image_uses_the_size_of_the_object_by_default(
    page: PageController, plate: FakePlate, monkeypatch, _plate_source
):
    monkeypatch.setattr(image, "OPENHASP_IMAGE_HOST", "127.0.0.1")
    img = await page.add_image(obj_id=45)

    await img.push_image(image=str(IMAGE))
    await img.push_image(image=str(IMAGE))
    await plate.settle()

    # the plate is asked once; the 50x50 image covers the 20x10 of the object
    assert [read for read in _plate_source if read[1] in ("w", "h")] == [("p1b45", "w"), ("p1b45", "h")]
    assert [len(data) for data in plate.downloaded_images] == [4 + 20 * 10 * 2] * 2


async def test_reads_of_an_object_do_not_overlap(page: PageController, plate: FakePlate, monkeypatch):
    """The plate answers all reads of an object on one topic: overlapping ones would get each other's answers."""
    monkeypatch.setattr(image, "OPENHASP_IMAGE_HOST", "127.0.0.1")
    running = 0
    most_running = 0

    async def get_object_property(self, obj, prop, timeout=1.0):
        nonlocal running, most_running
        running += 1
        most_running = max(most_running, running)
        await asyncio.sleep(0.01)
        running -= 1
        return {"w": 20, "h": 10}.get(prop, PLACEHOLDER)

    monkeypatch.setattr(OpenHaspClient, "get_object_property", get_object_property)
    img = await page.add_image(obj_id=45)

    await asyncio.gather(img.push_image(image=str(IMAGE)), img.push_image(image=str(IMAGE)), img.restore_default_source())
    await plate.settle()

    assert most_running == 1
    assert [len(data) for data in plate.downloaded_images] == [4 + 20 * 10 * 2] * 2


async def test_push_image_takes_the_missing_size_from_the_object(page: PageController, plate: FakePlate, monkeypatch):
    monkeypatch.setattr(image, "OPENHASP_IMAGE_HOST", "127.0.0.1")
    img = await page.add_image(obj_id=45)

    await img.push_image(image=str(IMAGE), height=4)
    await plate.settle()

    # the width of the object, 20
    assert [len(data) for data in plate.downloaded_images] == [4 + 20 * 4 * 2]


async def test_push_image_logs_an_error_if_the_plate_does_not_know_the_size(
    page: PageController, plate: FakePlate, monkeypatch, caplog
):
    async def unknown(self, obj, prop, timeout=1.0):
        return None

    monkeypatch.setattr(OpenHaspClient, "get_object_property", unknown)
    img = await page.add_image(obj_id=45)

    await img.push_image(image=str(IMAGE))

    assert plate.commands == []
    assert "did not report the size" in caplog.text


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
        "p1b45.offset_x=1",
        "p1b45.offset_y=2",
        "p1b45.offset_x=0",
        "p1b45.offset_y=0",
        "p1b45.zoom=128",
        "p1b45.zoom=256",
        "p1b45.angle=458",
        "p1b45.angle=0",
        "p1b45.pivot_x=3",
        "p1b45.pivot_y=4",
        "p1b45.pivot_x=0",
        "p1b45.pivot_y=0",
        "p1b45.antialias=True",
        "p1b45.antialias=False",
    ]


async def test_default_source_is_restored_after_an_image_was_pushed(page: PageController, plate: FakePlate, monkeypatch):
    monkeypatch.setattr(image, "OPENHASP_IMAGE_HOST", "127.0.0.1")
    img = await page.add_image(obj_id=45)
    await img.push_image(image=str(IMAGE), width=10, height=10)
    await plate.settle()

    assert await img.restore_default_source()
    # an image of the same object pushed again, and the default is restored again
    await img.push_image(image=str(IMAGE), width=10, height=10)
    await plate.settle()
    assert await img.restore_default_source()

    assert [c.split("=")[1] if "http" not in c else "pushed" for c in plate.commands] == [
        "pushed",
        PLACEHOLDER,
        "pushed",
        PLACEHOLDER,
    ]


async def test_default_source_is_read_once_before_the_first_push(
    page: PageController, plate: FakePlate, monkeypatch, _plate_source
):
    monkeypatch.setattr(image, "OPENHASP_IMAGE_HOST", "127.0.0.1")
    img = await page.add_image(obj_id=45)

    await img.push_image(image=str(IMAGE), width=10, height=10)
    await plate.settle()
    await img.push_image(image=str(IMAGE), width=10, height=10)
    await plate.settle()
    await img.restore_default_source()

    assert _plate_source == [("p1b45", "src")]


async def test_default_source_can_be_restored_before_anything_was_pushed(page: PageController, plate: FakePlate):
    img = await page.add_image(obj_id=45)

    assert await img.restore_default_source()

    assert plate.commands == [f"p1b45.src={PLACEHOLDER}"]


@pytest.mark.parametrize("answer", [None, "", "http://192.168.2.10:20000/0f1e2d3c"])
async def test_object_without_a_configured_image_has_no_default_source(
    page: PageController, plate: FakePlate, monkeypatch, answer
):
    async def get_object_property(self, obj, prop, timeout=1.0):
        return answer

    monkeypatch.setattr(OpenHaspClient, "get_object_property", get_object_property)
    img = await page.add_image(obj_id=45)

    assert not await img.restore_default_source()

    assert plate.commands == []
