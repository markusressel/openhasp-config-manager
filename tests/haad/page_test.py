import pytest
from haad.hass.entity import HAEntity

from openhasp_config_manager.haad.objects.button import ButtonObjectController, SceneButtonObjectController
from openhasp_config_manager.haad.objects.image import ImageObjectController
from openhasp_config_manager.haad.objects.label import LabelObjectController
from openhasp_config_manager.haad.objects.progress import BarObjectController
from openhasp_config_manager.haad.objects.slider import SliderObjectController
from openhasp_config_manager.haad.objects.switch import SwitchObjectController
from openhasp_config_manager.haad.page import PageController
from tests.haad.conftest import PLACEHOLDER_ID
from tests.haad.fakes import FakePlate


async def test_add_methods_create_object_controllers(page: PageController, plate: FakePlate):
    async def on_click():
        pass

    added = [
        await page.add_label(obj_id=1),
        await page.add_button(obj_id=2, on_click=on_click),
        await page.add_scene_button(obj_id=3, scene="work"),
        await page.add_switch(obj_id=4),
        await page.add_slider(obj_id=5),
        await page.add_bar(obj_id=6),
        await page.add_image(obj_id=7),
    ]

    assert [type(o) for o in added] == [
        LabelObjectController, ButtonObjectController, SceneButtonObjectController, SwitchObjectController,
        SliderObjectController, BarObjectController, ImageObjectController,
    ]
    assert page.objects == {PLACEHOLDER_ID: page.objects[PLACEHOLDER_ID], **{o.obj_id: o for o in added}}
    assert all(o.page == 1 and o.client is page.client and o.state_updater is page.state_updater for o in added)
    # adding sends nothing, initialize_objects() binds them
    assert plate.commands == []


async def test_add_object_with_existing_id_raises(page: PageController):
    await page.add_label(obj_id=1)

    with pytest.raises(ValueError, match="Object with id 1 already exists on page 1"):
        await page.add_switch(obj_id=1)


async def test_initialize_objects_initializes_in_order(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.a", "a")
    await simulator.ha.trigger_state_change("sensor.b", "b")
    await page.add_label(obj_id=2, entity="sensor.b")
    await page.add_label(obj_id=1, entity="sensor.a")

    await page.initialize_objects()

    assert plate.commands == ["p1b2.text=b", "p1b2.text=b", "p1b1.text=a", "p1b1.text=a"]


async def test_register_objects_does_nothing_by_default(page: PageController):
    await PageController.register_objects(page)


async def test_go_to_this_page(page: PageController, plate: FakePlate):
    await page.go_to_this_page()

    assert plate.commands == ["page 1"]


async def test_entity_accepts_ha_entities_ids_and_lists(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("sensor.a", "a")
    await simulator.ha.trigger_state_change("sensor.b", "b")

    labels = [
        await page.add_label(obj_id=1, entity=HAEntity("sensor.a")),
        await page.add_label(obj_id=2, entity="sensor.a"),
        await page.add_label(obj_id=3, entity=[HAEntity("sensor.a"), "sensor.b"]),
    ]
    bar = await page.add_bar(obj_id=4, entity=HAEntity("sensor.a"))

    assert [label._entity_ids for label in labels] == [["sensor.a"], ["sensor.a"], ["sensor.a", "sensor.b"]]
    assert bar._entity_id == "sensor.a"
