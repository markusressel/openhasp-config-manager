"""Plates without an openhasp-configs directory (README §4.1)."""
import pytest

from openhasp_config_manager.haad.plate import GuiDefaults, PlateConfig, PlateController, Screen
from openhasp_config_manager.haad.plate.device_factory import MqttBroker, build_device
from tests.haad.conftest import PlateUnderTest, page_at
from tests.haad.fakes import FakeOpenHaspClient, FakePlate, Http

BROKER = MqttBroker(host="broker", port=1883, user="haad", password="secret")
SETTINGS = {"host": "192.168.5.172", "mqtt_name": "mqtt_name", "http_user": "admin", "http_password": "pw"}
CONFIG = PlateConfig(screen=Screen(width=320, height=480), gui=GuiDefaults(idle1=30, idle2=120))


class CodePlate(PlateUnderTest):
    @property
    def plate_config(self) -> PlateConfig:
        return CONFIG


def test_build_device():
    device = build_device("plate3", SETTINGS, CONFIG, BROKER)

    config = device.config
    assert device.name == "plate3"
    assert config.openhasp_config_manager.device.ip == "192.168.5.172"
    assert (config.openhasp_config_manager.device.screen.width, config.openhasp_config_manager.device.screen.height) == (320, 480)
    assert (config.mqtt.name, config.mqtt.host, config.mqtt.port, config.mqtt.user, config.mqtt.password) == \
           ("mqtt_name", "broker", 1883, "haad", "secret")
    assert (config.http.user, config.http.password) == ("admin", "pw")
    assert (config.gui.idle1, config.gui.idle2, config.gui.rotate) == (30, 120, None)


def test_build_device_with_own_broker_and_without_gui():
    settings = {**SETTINGS, "mqtt": {"host": "other", "port": 8883, "user": "u", "password": "p"}}

    config = build_device("plate3", settings, PlateConfig(screen=Screen(1, 2)), BROKER).config

    assert (config.mqtt.host, config.mqtt.port, config.mqtt.user, config.mqtt.password) == ("other", 8883, "u", "p")
    assert config.gui.idle1 is None


def test_build_device_needs_settings_and_screen():
    with pytest.raises(KeyError, match="Missing settings of plate 'plate3' in haad.yaml \\(controllers.plate3\\): http_user, http_password"):
        build_device("plate3", {"host": "h", "mqtt_name": "m"}, CONFIG, BROKER)
    with pytest.raises(ValueError, match="needs a screen=Screen"):
        build_device("plate3", SETTINGS, PlateConfig(), BROKER)


async def test_plate_without_config_dir(simulator, start_plate, plate: FakePlate):
    simulator.config.CONTROLLERS.value = {"plate3": SETTINGS}
    simulator.config.MQTT_BROKER.value = "broker"
    simulator.config.MQTT_USERNAME.value = "haad"
    simulator.config.MQTT_PASSWORD.value = "secret"

    controller = await start_plate(CodePlate, pages=[page_at(1)], name="plate3", config_dir=None)

    plate_controller = controller.plate_controller
    assert plate_controller.deployment_controller is None
    assert isinstance(plate_controller.client, FakeOpenHaspClient)
    assert plate_controller.device.config.mqtt.host == "broker"
    assert plate_controller.screen == Screen(320, 480)
    assert plate.traffic[:2] == [Http("GET", "list?dir=/"), Http("POST", "config", {"idle1": 30, "idle2": 120, "save": "gui"})]


async def test_plate_without_config_dir_needs_a_device(page):
    with pytest.raises(ValueError, match="needs a config_dir or a device"):
        PlateController(controller=page.controller, state_updater=page.state_updater, name="x", config_dir=None)


def test_create_client():
    from openhasp_config_manager.haad.plate.device_factory import create_client
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    client = create_client(build_device("plate3", SETTINGS, CONFIG, BROKER))

    assert type(client) is OpenHaspClient
