from types import SimpleNamespace

import pytest

pytest.importorskip("appdaemon")

from openhasp_config_manager.ad.plate import PlateController  # noqa: E402
from openhasp_config_manager.ad.plate.deployment import DeploymentController  # noqa: E402
from openhasp_config_manager.ad.plate.screen import ScreenController  # noqa: E402


class RecordingClient:
    """Like OpenHaspClient: `set_gui_config` is a coroutine function, so it only does something when it is awaited."""

    def __init__(self):
        self.sent = []

    async def set_gui_config(self, config):
        self.sent.append(config)


def _deployment_controller(client: RecordingClient) -> DeploymentController:
    controller = object.__new__(DeploymentController)
    controller.client = client
    controller.device = SimpleNamespace(config=SimpleNamespace(gui="gui-config"))
    return controller


async def test_deploy_config_sends_the_gui_config():
    client = RecordingClient()

    await _deployment_controller(client).deploy_config()

    assert client.sent == ["gui-config"]


async def test_default_auto_brightness_config_sends_the_gui_config():
    client = RecordingClient()
    screen = ScreenController(app=None, client=client, deployment_controller=_deployment_controller(client))

    await screen.set_default_auto_brightness_config()

    assert client.sent == ["gui-config"]


async def test_set_gui_config2_sends_the_gui_config():
    client = RecordingClient()
    controller = object.__new__(PlateController)
    controller.deployment_controller = _deployment_controller(client)

    await controller.set_gui_config2(idle1=1, idle2=2, rotate=3, cursor=4, bckl=5)

    assert [(c.idle1, c.idle2, c.rotate, c.cursor, c.bckl) for c in client.sent] == [(1, 2, 3, 4, 5)]
