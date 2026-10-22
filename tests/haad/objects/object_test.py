import pytest

from haad import HaadStateEvent

from openhasp_config_manager.haad.objects import ObjectController
from openhasp_config_manager.haad.objects.checkbox import CheckboxObjectController
from openhasp_config_manager.haad.page import PageController
from tests.haad.fakes import FakePlate


def _object(page: PageController, cls=ObjectController, **kwargs) -> ObjectController:
    return cls(
        controller=page.controller, client=page.client, state_updater=page.state_updater, page=page.index, obj_id=5, **kwargs
    )


async def test_object_id(page: PageController):
    assert _object(page).object_id == "p1b5"


async def test_object_init_is_abstract(page: PageController):
    with pytest.raises(NotImplementedError):
        await _object(page).init()


async def test_set_object_properties_deduplicates(page: PageController, plate: FakePlate):
    obj = _object(page)

    await obj.set_object_properties({"a": 1, "b": "x"})
    await obj.set_object_properties({"a": 1, "b": "y"})
    await obj.set_object_properties({"a": 1})
    await obj.set_object_properties({"a": 1}, force=True)
    obj.clear_cache()
    await obj.set_object_properties({"b": "y"})

    assert plate.commands == ["p1b5.a=1", "p1b5.b=x", "p1b5.b=y", "p1b5.a=1", "p1b5.b=y"]


async def test_set_enabled_and_hidden(page: PageController, plate: FakePlate):
    obj = _object(page)

    await obj.set_enabled(False)
    await obj.set_enabled(False)
    # set_hidden() is not de-duplicated
    await obj.set_hidden(True)
    await obj.set_hidden(True)
    await obj.set_hidden(False)

    assert plate.commands == ["p1b5.enabled=False", "p1b5.hidden=1", "p1b5.hidden=1", "p1b5.hidden=0"]


async def test_checkbox_follows_its_entity(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("input_boolean.x", "on")
    checkbox = _object(page, CheckboxObjectController, entity_id="input_boolean.x")

    await checkbox.init()
    await plate.settle()
    await simulator.ha.trigger_state_change("input_boolean.x", "off")
    await plate.settle()
    # haad's EntityTrigger does not report changes to unavailable
    await simulator.ha.trigger_state_change("input_boolean.x", "unavailable")
    await plate.settle()

    assert list(page.state_updater._registered_objects) == ["checkbox:p1b5:input_boolean.x"]
    assert plate.commands == ["p1b5.enabled=True", "p1b5.text=on", "p1b5.text=off"]


async def test_checkbox_is_disabled_while_its_entity_is_unavailable(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("input_boolean.x", "unavailable")
    checkbox = _object(page, CheckboxObjectController, entity_id="input_boolean.x")

    await checkbox.init()
    await plate.settle()

    assert plate.commands == ["p1b5.enabled=False"]


async def test_checkbox_follows_an_attribute(simulator, page: PageController, plate: FakePlate):
    await simulator.ha.trigger_state_change("input_boolean.x", "on", {"a": 3})
    checkbox = _object(page, CheckboxObjectController, entity_id="input_boolean.x", attribute="a")

    await checkbox.init()
    await plate.settle()

    assert plate.commands == ["p1b5.enabled=True", "p1b5.text=3"]


async def test_checkbox_without_a_state_source_registers_nothing(page: PageController, plate: FakePlate):
    checkbox = _object(page, CheckboxObjectController)

    await checkbox.init()

    assert page.state_updater._registered_objects == {}
    assert plate.commands == []


async def test_checkbox_state_sources(simulator, page: PageController):
    """The getter registered with the StateUpdater: get_state, then the attribute, then the state."""
    await simulator.ha.trigger_state_change("input_boolean.x", "on", {"a": 3})

    async def get_state():
        return "from get_state"

    getters = []
    for kwargs in [dict(get_state=get_state), dict(entity_id="input_boolean.x", attribute="a")]:
        checkbox = _object(page, CheckboxObjectController, **kwargs)
        page.state_updater.clear()
        await checkbox.init()
        getters.append(next(iter(page.state_updater._registered_objects.values()))["get"])

    assert [await getter() for getter in getters] == ["from get_state", 3]


async def test_checkbox_property_setters(page: PageController, plate: FakePlate):
    checkbox = _object(page, CheckboxObjectController)

    await checkbox.set_text("abc")
    await checkbox.set_is_checked(True)
    await checkbox.set_is_checked(False)

    assert plate.commands == ["p1b5.text=abc", "p1b5.val=1", "p1b5.val=0"]


async def test_checkbox_state_change_handler(page: PageController, plate: FakePlate):
    checkbox = _object(page, CheckboxObjectController, converter=lambda x: f"<{x}>")

    await checkbox._on_state_changed(HaadStateEvent(None, None, None, "unavailable", None))
    await checkbox._on_state_changed(HaadStateEvent(None, None, None, "on", None))

    assert plate.commands == ["p1b5.enabled=False", "p1b5.enabled=True", "p1b5.text=<on>"]
