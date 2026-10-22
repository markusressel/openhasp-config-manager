"""
Golden-master scenarios: one page per page shape in haad-home (`controllers/openhasp/page/`), rebuilt here without its
dependencies, with the complete traffic of a start and of the events that follow.
"""
from datetime import timedelta
from typing import Any

from haad.triggers import Trigger
from openhasp_config_manager.haad.page import PageController
from tests.haad.conftest import page_at
from tests.haad.fakes import FakePlate, Http, Mqtt

TIME_ENTITY = "sensor.time"
GUI_DEFAULTS = Http("POST", "config", {"idle1": 60, "idle2": 120, "rotate": 1, "cursor": 0, "bckl": 32, "save": "gui"})
ALWAYS_ON = [Http("POST", "config", {"idle1": 15, "idle2": 0, "save": "gui"}), Mqtt("hasp/mqtt_name/command/idle", "short")]


def _cmd(payload: str) -> Mqtt:
    return Mqtt("hasp/mqtt_name/command", payload)


class HeaderPage(PageController):
    """Like haad-home's MarkusPageController: a clock in the header."""

    async def register_header_clock(self, obj_id: int = 10):
        return await self.add_label(obj_id=obj_id, entity=TIME_ENTITY)


class ClockPage(HeaderPage):
    async def register_objects(self):
        await self.register_header_clock()


class RoomPage(HeaderPage):
    """Like the Markus and bathroom pages: converters, attributes, icons, a property following another entity, switches, scenes."""

    async def register_objects(self):
        await self.register_header_clock()
        self.co2_text = await self.add_label(obj_id=12, entity="sensor.co2", text=lambda x: f"{int(float(x))}ppm")
        await self.controller.react_to(action=self._on_co2_changed, trigger="sensor.co2", immediately=True)
        await self.add_label(obj_id=13, entity="climate.room", attribute="current_temperature", text=lambda x: f"{float(x)}°C")
        await self.add_label(obj_id=20, entity="light.desk", text=lambda x: "\uE6E8" if x == "on" else "\uE335")
        await self.add_scene_button(obj_id=17, scene="sleeping")
        await self.add_switch(obj_id=22, entity="light.desk")

    async def _on_co2_changed(self):
        co2 = float(await self.controller.ha.get_state("sensor.co2"))
        if co2 > 1000:
            await self.co2_text.set_border_width(3)
            await self.plate.wakeup()
        else:
            await self.co2_text.set_border_width(0)


async def test_room_page(simulator, start_plate, plate: FakePlate):
    for entity_id, state, attributes in [
        (TIME_ENTITY, "12:00", None), ("sensor.co2", "800", None), ("climate.room", "heat", {"current_temperature": 21}),
        ("light.desk", "on", None),
    ]:
        await simulator.ha.trigger_state_change(entity_id, state, attributes)

    await start_plate(pages=[page_at(1, RoomPage)])

    assert plate.traffic == [
        Http("GET", "list?dir=/"),
        GUI_DEFAULTS,
        *[_cmd(c) for c in [
            # register_objects()'s own reaction runs before the objects are initialized
            "p1b12.border_width=0",
            "p1b10.text=12:00", "p1b10.text=12:00",
            "p1b12.text=800ppm", "p1b12.text=800ppm",
            "p1b13.text=21.0°C", "p1b13.text=21.0°C",
            "p1b20.text=\uE6E8", "p1b20.text=\uE6E8",
            "p1b22.val=1", "p1b22.enabled=True",
            # first sync, one second later (the switch's sync fails, see switch_test.py)
            "p1b10.text=12:00", "p1b12.text=800ppm", "p1b13.text=21.0°C", "p1b20.text=\uE6E8",
        ]],
    ]

    plate.clear()
    await simulator.ha.trigger_state_change("sensor.co2", "1200")
    await simulator.ha.trigger_state_change("light.desk", "off")
    await plate.settle()
    assert plate.commands == [
        "p1b12.border_width=3", "idle off", "p1b12.text=1200ppm",
        # the first sync cleared the caches and the switch's sync failed, so "enabled" is sent again
        "p1b20.text=\uE335", "p1b22.val=0", "p1b22.enabled=True",
    ]


class PrinterPage(HeaderPage):
    """Like the 3D printer page: values from get_state on triggers, static texts, a ticking value, colours, a button, a bar."""

    async def register_objects(self):
        await self.register_header_clock()
        self.events = []
        self.nozzle = await self.add_label(obj_id=12, entity="sensor.nozzle", get_state=self._nozzle,
                                           text=lambda x: f"T: {int(float(x))}°C")
        await self.controller.react_to(action=self._on_nozzle_target_changed, trigger="number.nozzle_target", immediately=True)
        status = await self.add_label(obj_id=26, entity="sensor.stage", get_state=self._status)
        await status.set_mode("scroll")
        await self.add_label(obj_id=29, entity="sensor.start_time", text=lambda x: "Elapsed:")
        await self.add_label(obj_id=30, entity="sensor.time_second", get_state=self._elapsed)
        await self.add_bar(obj_id=28, entity="sensor.progress", transform_value=lambda x: int(float(x)))
        await self.add_button(obj_id=20, on_click=self._on_pause)
        image = await self.add_image(obj_id=45)
        await image.set_hidden(False)
        await self.claim(active=self._printing, trigger="sensor.stage", keep_awake=True)
        await self.controller.react_to(action=self._on_stage_changed, trigger="sensor.stage", immediately=True)

    async def _nozzle(self) -> Any:
        return await self.controller.ha.get_state("sensor.nozzle")

    async def _status(self) -> str:
        return f"Stage: {await self.controller.ha.get_state('sensor.stage')}"

    async def _elapsed(self) -> str:
        return f"{await self.controller.ha.get_state('sensor.time_second')}s"

    async def _on_nozzle_target_changed(self, event):
        if float(event.new) > 0:
            await self.nozzle.set_color("#B22222")
        else:
            await self.nozzle.set_color("#FFFFFF")

    async def _printing(self) -> bool:
        return await self.controller.ha.get_state("sensor.stage") == "printing"

    async def _on_stage_changed(self, event):
        if event.new != "printing":
            await self.client.wakeup()

    async def _on_pause(self):
        self.events.append("pause")


async def test_printer_page(simulator, start_plate, plate: FakePlate):
    for entity_id, state in [
        (TIME_ENTITY, "12:00"), ("sensor.nozzle", "25.4"), ("number.nozzle_target", "0"), ("sensor.stage", "idle"),
        ("sensor.start_time", "x"), ("sensor.time_second", "0"), ("sensor.progress", "0"),
    ]:
        await simulator.ha.trigger_state_change(entity_id, state)

    controller = await start_plate(pages=[page_at(1, ClockPage), page_at(2, PrinterPage)])
    page = controller.plate_controller.pages[2]

    assert plate.traffic == [
        Http("GET", "list?dir=/"),
        GUI_DEFAULTS,
        # page 1: register_objects(), initialize_objects()
        _cmd("p1b10.text=12:00"), _cmd("p1b10.text=12:00"),
        # page 2: register_objects() with its own reactions; the stage is idle: drop the (not requested) behaviour and wake
        # up the plate
        *[_cmd(c) for c in ["p2b12.text_color=#FFFFFF", "p2b26.mode=scroll", "p2b45.hidden=0"]],
        Mqtt("hasp/mqtt_name/command/idle", "off"),
        # page 2: initialize_objects()
        *[_cmd(c) for c in [
            "p2b10.text=12:00", "p2b10.text=12:00",
            "p2b12.text=T: 25°C", "p2b12.text=T: 25°C",
            "p2b26.text=Stage: idle", "p2b26.text=Stage: idle",
            "p2b29.text=Elapsed:", "p2b29.text=Elapsed:",
            "p2b30.text=0s", "p2b30.text=0s",
            "p2b28.enabled=True", "p2b28.val=0",
            # first sync
            "p1b10.text=12:00", "p2b10.text=12:00", "p2b12.text=T: 25°C", "p2b26.text=Stage: idle", "p2b29.text=Elapsed:",
            "p2b30.text=0s", "p2b28.enabled=True", "p2b28.val=0",
        ]],
    ]

    plate.clear()
    await simulator.ha.trigger_state_change("number.nozzle_target", "220")
    await simulator.ha.trigger_state_change("sensor.stage", "printing")
    await simulator.ha.trigger_state_change("sensor.time_second", "1")
    await simulator.ha.trigger_state_change("sensor.progress", "12.5")
    await plate.send("state/p2b20", {"event": "up"})
    assert plate.traffic == [
        _cmd("p2b12.text_color=#B22222"),
        *ALWAYS_ON,
        Mqtt("hasp/mqtt_name/command/page", "2"),
        _cmd("p2b26.text=Stage: printing"),
        _cmd("p2b30.text=1s"),
        _cmd("p2b28.val=12"),
    ]
    assert page.events == ["pause"]


class MediaPage(HeaderPage):
    """Like the media page: labels on a list of entities, a bar and its label refreshed every second, page behaviours."""

    async def register_objects(self):
        await self.register_header_clock()
        players = ["media_player.a", "media_player.b"]
        await self.add_label(obj_id=25, entity=players, attribute="all", get_state=self._artist)
        self.bar = await self.add_bar(obj_id=30)
        self.bar_label = await self.add_label(obj_id=31)
        await self.controller.react_to(action=self._tick, trigger=Trigger.Time.every(interval=timedelta(seconds=1)),
                                       immediately=True)
        await self.claim(active=self._any_playing, trigger=Trigger.Entity(players, attribute="all"), keep_awake=True)

    async def _playing(self) -> list:
        return [p for p in ["media_player.a", "media_player.b"] if await self.controller.ha.get_state(p) == "playing"]

    async def _artist(self) -> str:
        playing = await self._playing()
        if not playing:
            return "-"
        return await self.controller.ha.get_state(playing[0], attribute="media_artist")

    async def _tick(self):
        position = await self.controller.ha.get_state("sensor.position")
        if position is None:
            await self.bar.set_enabled(False)
            await self.bar.set_progress(0)
            await self.bar_label.set_text("")
        else:
            await self.bar.set_enabled(True)
            await self.bar.set_progress(position)
            await self.bar_label.set_text(f"{position}%")

    async def _any_playing(self) -> bool:
        return bool(await self._playing())


async def test_media_page(simulator, start_plate, plate: FakePlate):
    await simulator.ha.trigger_state_change(TIME_ENTITY, "12:00")
    await simulator.ha.trigger_state_change("media_player.a", "idle")
    await simulator.ha.trigger_state_change("media_player.b", "idle")

    await start_plate(pages=[page_at(1, MediaPage)])

    assert plate.traffic == [
        Http("GET", "list?dir=/"),
        GUI_DEFAULTS,
        *[_cmd(c) for c in [
            "p1b30.enabled=False", "p1b30.val=0", "p1b31.text=",
            "p1b10.text=12:00", "p1b10.text=12:00",
            "p1b25.text=-", "p1b25.text=-", "p1b25.text=-",
            # the tick one second later, then the first sync
            "p1b31.text=",
            "p1b10.text=12:00", "p1b25.text=-",
        ]],
    ]

    plate.clear()
    await simulator.ha.trigger_state_change("sensor.position", "40")
    await simulator.ha.trigger_state_change("media_player.b", "playing", {"media_artist": "Artist"})
    await plate.settle()
    await simulator.advance(timedelta(seconds=1))
    await plate.settle()
    # the page's reaction was registered before the label's (register_objects() runs before initialize_objects())
    assert plate.traffic == [
        *ALWAYS_ON,
        Mqtt("hasp/mqtt_name/command/page", "1"),
        _cmd("p1b25.text=Artist"),
        _cmd("p1b30.enabled=True"), _cmd("p1b30.val=40"), _cmd("p1b31.text=40%"),
    ]

    plate.clear()
    await simulator.ha.trigger_state_change("media_player.b", "idle", {})
    await plate.settle()
    assert plate.traffic == [
        Http("POST", "config", {"idle1": 60, "idle2": 120, "save": "gui"}),
        Mqtt("hasp/mqtt_name/command/idle", "off"),
        _cmd("p1b25.text=-"),
    ]
    simulator.ha.assert_service_called("mqtt/publish", data_contains={"topic": "hasp/test_device/config/gui"})


class AboutPage(HeaderPage):
    """Like the about page: a button that reboots the plate."""

    async def register_objects(self):
        await self.register_header_clock()

        await self.add_button(obj_id=50, on_click=self.plate.reboot)


async def test_about_page(simulator, start_plate, plate: FakePlate):
    await simulator.ha.trigger_state_change(TIME_ENTITY, "12:00")
    await start_plate(pages=[page_at(3, AboutPage)])
    plate.clear()

    await plate.send("state/p3b50", {"event": "down"})
    await plate.send("state/p3b50", {"event": "up"})

    assert plate.traffic == [Http("GET", "reboot")]
