import logging

from openhasp_config_manager.haad.page import PageController
from tests.haad.fakes import FakePlate


async def test_button_calls_on_click_on_up_events(page: PageController, plate: FakePlate):
    clicks = []

    async def on_click():
        clicks.append("click")

    button = await page.add_button(obj_id=20, on_click=on_click)
    await button.init()

    await plate.send("state/p1b20", {"event": "down"})
    await plate.send("state/p1b20", {"event": "up", "val": 0})
    await plate.send("state/p1b21", {"event": "up"})

    assert clicks == ["click"]
    assert plate.commands == []


async def test_button_property_setters(page: PageController, plate: FakePlate):
    async def on_click():
        pass

    button = await page.add_button(obj_id=20, on_click=on_click)

    await button.set_is_toggle(True)
    await button.set_is_toggled(True)
    await button.set_is_toggled(False)
    await button.set_is_toggled(False)
    await button.set_text("Pause")
    await button.set_text_align("center")

    assert plate.commands == [
        "p1b20.toggle=True",
        "p1b20.val=1",
        "p1b20.val=0",
        "p1b20.text=Pause",
        "p1b20.align=center",
    ]


async def test_scene_button_click_fails_and_drops_the_mqtt_connection(
    simulator, page: PageController, plate: FakePlate, caplog
):
    """
    HaadController has no call_service(): the click raises inside the MQTT message handler, which ends the client's MQTT
    connection (MqttClient reconnects after 5 seconds). No scene is activated.
    """
    button = await page.add_scene_button(obj_id=17, scene="sleeping")
    await button.init()
    assert button.scene == "sleeping"

    with caplog.at_level(logging.INFO):
        await plate.send("state/p1b17", {"event": "up"})

    assert "Activating scene scene.sleeping" in caplog.text
    assert "object has no attribute 'call_service'" in caplog.text
    assert not plate.subscribed
    assert simulator.ha.called_services == []


async def test_scene_button_keeps_scene_prefix(page: PageController, plate: FakePlate, caplog):
    button = await page.add_scene_button(obj_id=17, scene="scene.work")
    await button.init()

    with caplog.at_level(logging.INFO):
        await plate.send("state/p1b17", {"event": "up"})

    assert "Activating scene scene.work" in caplog.text
