import pytest

from haad import HaadStateEvent

from openhasp_config_manager.haad.objects import ObjectController
from openhasp_config_manager.haad.objects.checkbox import CheckboxObjectController
from openhasp_config_manager.haad.page import PageController
from tests.haad.fakes import FakePlate


def _object(page: PageController, cls=ObjectController, **kwargs) -> ObjectController:
    return cls(controller=page.controller, client=page.client, state_updater=page.state_updater, page=page.index, obj_id=5,
               **kwargs)


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


async def test_checkbox_init_fails(simulator, page: PageController, plate: FakePlate, caplog):
    """
    CheckboxObjectController is not used by any page (PageController has no add_checkbox) and is broken: its sync passes
    the whole state cache to a HaadStateEvent with missing arguments, and with an entity, EntityTrigger is not imported.
    """
    await simulator.ha.trigger_state_change("input_boolean.x", "on")
    checkbox = _object(page, CheckboxObjectController, entity_id="input_boolean.x")

    with pytest.raises(NameError, match="EntityTrigger"):
        await checkbox.init()

    assert list(page.state_updater._registered_objects) == ["checkbox:p1b5:input_boolean.x"]
    assert "HaadStateEvent" in caplog.text
    assert plate.commands == []


async def test_checkbox_init_without_entity(page: PageController, plate: FakePlate, caplog):
    checkbox = _object(page, CheckboxObjectController)

    await checkbox.init()

    assert list(page.state_updater._registered_objects) == ["checkbox:p1b5:None"]
    assert "HaadStateEvent" in caplog.text


async def test_checkbox_init_with_attribute_fails(simulator, page: PageController, caplog):
    checkbox = _object(page, CheckboxObjectController, entity_id="input_boolean.x", attribute="a")

    with pytest.raises(NameError, match="EntityTrigger"):
        await checkbox.init()


async def test_checkbox_state_sources(simulator, page: PageController):
    """The getter registered with the StateUpdater: get_state, then the attribute, then the state."""
    await simulator.ha.trigger_state_change("input_boolean.x", "on", {"a": 3})

    async def get_state():
        return "from get_state"

    getters = []
    for kwargs in [dict(get_state=get_state), dict(entity_id="input_boolean.x", attribute="a")]:
        checkbox = _object(page, CheckboxObjectController, **kwargs)
        page.state_updater.clear()
        try:
            await checkbox.init()
        except NameError:
            pass
        getters.append(next(iter(page.state_updater._registered_objects.values()))["get"])

    assert [await getter() for getter in getters] == ["from get_state", 3]


async def test_checkbox_property_setters(page: PageController, plate: FakePlate):
    checkbox = _object(page, CheckboxObjectController)

    await checkbox.set_text("abc")
    await checkbox.set_is_checked(True)
    await checkbox.set_is_checked(False)

    assert plate.commands == ["p1b5.text=abc", "p1b5.val=1", "p1b5.val=0"]


async def test_checkbox_without_any_state_source(page: PageController, plate: FakePlate):
    """Unreachable: init()'s check tests the bound getter method, which is never None."""
    checkbox = _object(page, CheckboxObjectController)
    checkbox._CheckboxObjectController__get_checkbox_state = None

    await checkbox.init()

    assert page.state_updater._registered_objects == {}


async def test_checkbox_state_change_handler(page: PageController, plate: FakePlate):
    """Unreachable today (see test_checkbox_init_fails): what the handler does with a state."""
    checkbox = _object(page, CheckboxObjectController, converter=lambda x: f"<{x}>")

    await checkbox._on_state_changed(HaadStateEvent(None, None, None, "unavailable", None))
    await checkbox._on_state_changed(HaadStateEvent(None, None, None, "on", None))

    assert plate.commands == ["p1b5.enabled=False", "p1b5.enabled=True", "p1b5.text=<on>"]
