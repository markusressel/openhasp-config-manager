import pytest

from openhasp_config_manager.haad.page import PageController
from openhasp_config_manager.haad.plate.deployment import DeploymentController
from tests.haad.conftest import CFG_ROOT
from tests.haad.fakes import FakeOpenHaspClient, FakePlate, Http


async def test_device_and_client_from_config_dir(page: PageController):
    deployment = page.plate.deployment_controller

    assert deployment.device.name == "test_device"
    assert deployment.config_dir == CFG_ROOT
    assert isinstance(deployment.client, FakeOpenHaspClient)
    assert page.client is deployment.client
    assert page.plate.screen_controller.client is deployment.client


async def test_unknown_device_raises(page: PageController, tmp_path):
    with pytest.raises(StopIteration):
        DeploymentController(controller=page.controller, name="unknown", config_dir=CFG_ROOT, output_dir=tmp_path)


async def test_deploy_uploads_the_generated_files_and_the_config(page: PageController, plate: FakePlate):
    plate.files = []

    assert await page.plate.deployment_controller.deploy(purge=False) is True

    assert [(request.method, request.url) for request in plate.http] == [
        ("GET", "list?dir=/"),
        ("POST", "edit"),
        ("POST", "edit"),
        ("POST", "edit"),
        ("GET", "api/config/mqtt/"),
        ("POST", "config"),
        ("GET", "api/config/http/"),
        ("POST", "config"),
        ("GET", "api/config/gui/"),
        ("POST", "config"),
    ]


async def test_deploy_config(page: PageController, plate: FakePlate):
    await page.plate.deployment_controller.deploy_config()

    assert plate.http == [
        Http("POST", "config", {"idle1": 60, "idle2": 120, "rotate": 1, "cursor": 0, "bckl": 32, "save": "gui"})
    ]


async def test_set_gui_config(page: PageController, plate: FakePlate):
    await page.plate.deployment_controller.set_gui_config(idle1=1, idle2=2, rotate=None, cursor=None, bckl=5)

    assert plate.commands == ['config/gui {"idle1": 1, "idle2": 2, "bckl": 5}']


async def test_screen_controller(page: PageController, plate: FakePlate):
    screen = page.plate.screen_controller

    await screen.set_backlight(state=False, brightness=3)
    await screen.set_idle(state="long")
    await screen.init()

    assert plate.commands == ['backlight {"state": false, "brightness": 3}', "idle long"]
    assert plate.http == [
        Http("POST", "config", {"idle1": 60, "idle2": 120, "rotate": 1, "cursor": 0, "bckl": 32, "save": "gui"})
    ]
