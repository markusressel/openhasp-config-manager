import logging

from openhasp_config_manager.haad.page.state_updater import StateUpdater


class _Controller:
    logger = logging.getLogger("test")


async def test_sync_all_and_by_name():
    updater = StateUpdater(controller=_Controller())
    calls = []

    def entry(name):
        async def get():
            calls.append(f"get {name}")
            return name.upper()

        async def update(state):
            calls.append(f"set {name} {state}")

        return get, update

    for name in ["a", "b"]:
        get, update = entry(name)
        updater.register(name=name, get_state=get, update_obj=update)

    await updater.sync()
    await updater.sync("b")

    assert calls == ["get a", "set a A", "get b", "set b B", "get b", "set b B"]


async def test_sync_unknown_name_and_empty_registry(caplog):
    updater = StateUpdater(controller=_Controller())

    with caplog.at_level(logging.INFO):
        await updater.sync()
        await updater.sync("x")

    assert "No registered objects to sync, ignoring request" in caplog.text
    assert "x not registered, ignoring request" in caplog.text


async def test_register_overwrites(caplog):
    updater = StateUpdater(controller=_Controller())
    calls = []

    async def get():
        return 1

    async def first(state):
        calls.append("first")

    async def second(state):
        calls.append("second")

    with caplog.at_level(logging.INFO):
        updater.register(name="a", get_state=get, update_obj=first)
        updater.register(name="a", get_state=get, update_obj=second)
        await updater.sync()

    assert calls == ["second"]
    assert "a already registered, overwriting existing entry" in caplog.text


async def test_sync_errors_are_logged_and_set_gets_none(caplog):
    """A failing getter still calls the setter, with None; a failing setter doesn't stop the other entries."""
    updater = StateUpdater(controller=_Controller())
    calls = []

    async def failing_get():
        raise RuntimeError("get failed")

    async def failing_set(state):
        calls.append(state)
        raise RuntimeError("set failed")

    async def get():
        return "ok"

    async def update(state):
        calls.append(state)

    updater.register(name="a", get_state=failing_get, update_obj=failing_set)
    updater.register(name="b", get_state=get, update_obj=update)
    await updater.sync()

    assert calls == [None, "ok"]
    assert "Error syncing a: Failed to retrieve current state: get failed" in caplog.text
    assert "Error syncing a: Failed to set state 'None': set failed" in caplog.text


async def test_clear():
    updater = StateUpdater(controller=_Controller())

    async def get():
        return 1

    async def update(state):
        raise AssertionError("cleared entries are not synced")

    updater.register(name="a", get_state=get, update_obj=update)
    updater.clear()
    await updater.sync()
