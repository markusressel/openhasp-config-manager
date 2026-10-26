import pytest

from tests import TestBase
from tests.gui.helpers import wait_until

pytest.importorskip("PyQt6")

from PyQt6.QtGui import QColor  # noqa: E402
from PyQt6.QtWidgets import QPushButton  # noqa: E402

from openhasp_config_manager.gui.domain.log_history import LogLinkState  # noqa: E402
from openhasp_config_manager.gui.qt.log_stream import LogStreamController  # noqa: E402
from openhasp_config_manager.gui.qt.theme import current_colors  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.log_view import LogView  # noqa: E402
from openhasp_config_manager.openhasp_client.logs import LogConnectionEvent, parse_log_line  # noqa: E402

ERROR = "[   1.000][1/2  3][4/5  6] FILE: Failed to open"
PLAIN = "[   2.000][1/2  3][4/5  6] HASP: Hello"


def _color_of(view: LogView, line: int, text: str) -> QColor:
    """:return: the foreground color of the first occurrence of the text in the given line"""
    block = view._text.document().findBlockByNumber(line)
    for fragment in (block.begin(),):
        while not fragment.atEnd():
            current = fragment.fragment()
            if text in current.text():
                return current.charFormat().foreground().color()
            fragment += 1
    raise AssertionError(f"{text!r} not found in line {line}")


class TestLogView(TestBase):
    def test_shows_the_lines_of_the_entries(self, qapp):
        # GIVEN
        view = LogView()

        # WHEN
        view.add_entries([parse_log_line(ERROR), parse_log_line(PLAIN)])

        # THEN
        assert view.text() == f"{ERROR}\n{PLAIN}"

    def test_the_level_gives_the_message_its_color(self, qapp):
        # GIVEN
        view = LogView()

        # WHEN
        view.add_entries([parse_log_line(ERROR), parse_log_line(PLAIN)])

        # THEN
        assert _color_of(view, 0, "Failed to open") == QColor(current_colors().error)
        assert _color_of(view, 1, "Hello") != QColor(current_colors().error)

    def test_the_filter_hides_other_entries_and_brings_them_back(self, qapp):
        # GIVEN
        view = LogView()
        view.add_entries([parse_log_line(ERROR), parse_log_line(PLAIN)])

        # WHEN
        view._filter.setText("hello")

        # THEN
        assert view.text() == PLAIN

        # WHEN: an entry arrives while filtering
        view.add_entries([parse_log_line("[   3.000] HASP: no match")])
        view.add_entries([parse_log_line("[   4.000] HASP: Hello again")])

        # THEN
        assert view.text() == f"{PLAIN}\n[   4.000] HASP: Hello again"

        # WHEN
        view._filter.setText("")

        # THEN
        assert len(view.text().splitlines()) == 4

    def test_clear(self, qapp):
        # GIVEN
        view = LogView()
        view.add_entries([parse_log_line(PLAIN)])

        # WHEN
        view.clear()
        view.add_entries([parse_log_line(ERROR)])

        # THEN
        assert view.text() == ERROR

    def test_follows_the_newest_entry_but_not_after_scrolling_up(self, qapp):
        # GIVEN
        view = LogView()
        view.resize(400, 120)
        view.show()
        view.add_entries([parse_log_line(f"[{i:4}.000] HASP: line {i}") for i in range(200)])
        bar = view._text.verticalScrollBar()

        # THEN
        assert bar.value() == bar.maximum()

        # WHEN
        bar.setValue(0)
        view.add_entries([parse_log_line("[ 999.000] HASP: more")])

        # THEN
        assert bar.value() == 0

        # WHEN: back at the end
        bar.setValue(bar.maximum())
        view.add_entries([parse_log_line("[ 999.000] HASP: even more")])

        # THEN
        assert bar.value() == bar.maximum()

    def test_the_hint_for_missing_colors_asks_to_enable_them(self, qapp):
        # GIVEN
        view = LogView()
        requests = []
        view.enableColorsRequested.connect(lambda: requests.append(True))
        view.show()

        # THEN
        assert view._colors_hint.isHidden()

        # WHEN
        view.set_colors_missing(True)
        view._colors_hint.findChild(QPushButton).click()

        # THEN
        assert not view._colors_hint.isHidden()
        assert requests == [True]

        # WHEN
        view.set_colors_missing(False)

        # THEN
        assert view._colors_hint.isHidden()

    def test_a_button_follows_the_log_again_after_scrolling_up(self, qapp):
        # GIVEN
        view = LogView()
        view.resize(400, 120)
        view.show()
        view.add_entries([parse_log_line(f"[{i:4}.000] HASP: line {i}") for i in range(200)])
        bar = view._text.verticalScrollBar()

        # THEN: following, so nothing to catch up
        assert not view.is_follow_button_visible()

        # WHEN
        bar.setValue(0)

        # THEN
        assert view.is_follow_button_visible()

        # WHEN: new entries don't move the view, and the button stays
        view.add_entries([parse_log_line("[ 999.000] HASP: more")])

        # THEN
        assert bar.value() == 0
        assert view.is_follow_button_visible()

        # WHEN
        view._follow_button.click()

        # THEN
        assert bar.value() == bar.maximum()
        assert not view.is_follow_button_visible()

        # WHEN: it follows again
        view.add_entries([parse_log_line("[ 999.000] HASP: even more")])

        # THEN
        assert bar.value() == bar.maximum()

    def test_scrolling_back_to_the_end_by_hand_hides_the_button(self, qapp):
        # GIVEN
        view = LogView()
        view.resize(400, 120)
        view.show()
        view.add_entries([parse_log_line(f"[{i:4}.000] HASP: line {i}") for i in range(200)])
        bar = view._text.verticalScrollBar()
        bar.setValue(0)

        # WHEN
        bar.setValue(bar.maximum())

        # THEN
        assert not view.is_follow_button_visible()

    def test_the_status_line(self, qapp):
        # GIVEN
        view = LogView()

        # WHEN
        view.set_link(LogLinkState.RECONNECTING, "reset")

        # THEN
        assert "reset" in view._status.text()
        assert view._status.property("role") == "error"


class _FakeClient:
    """Follows a log that sends the given items, then waits (a connection that stays open)."""

    created = []

    def __init__(self, device, items=()):
        self.device = device
        self.items = items
        self.started = False
        self.cancelled = False
        _FakeClient.created.append(self)

    async def follow_logs(self, reconnect=True):
        import asyncio

        assert reconnect
        self.started = True
        try:
            for item in self.items:
                yield item
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _Device:
    def __init__(self, name):
        self.name = name


class TestLogStreamController(TestBase):
    @pytest.fixture(autouse=True)
    def _stop_streams(self, async_loop):
        self._controllers = []
        yield
        for controller in self._controllers:
            controller.stop()
        wait_until(lambda: all(client.cancelled or not client.started for client in _FakeClient.created))

    def _controller(self, async_loop, items=()):
        _FakeClient.created = []
        controller = LogStreamController(client_factory=lambda device: _FakeClient(device, items))
        self._controllers.append(controller)
        entries, states, changed = [], [], []
        controller.entriesReceived.connect(entries.extend)
        controller.stateChanged.connect(lambda state, error: states.append((state, error)))
        controller.deviceChanged.connect(lambda: changed.append(True))
        return controller, entries, states, changed

    def test_there_is_no_connection_while_nobody_looks(self, async_loop):
        # GIVEN
        controller, entries, states, _ = self._controller(async_loop)

        # WHEN
        controller.set_device(_Device("plate"))

        # THEN
        assert controller.state == LogLinkState.INACTIVE
        assert _FakeClient.created == []

    def test_streams_while_active_and_stops_when_hidden(self, async_loop):
        # GIVEN
        controller, entries, states, _ = self._controller(
            async_loop, [LogConnectionEvent(True), parse_log_line(PLAIN), LogConnectionEvent(False, "reset")]
        )
        controller.set_device(_Device("plate"))

        # WHEN
        controller.set_active(True)

        # THEN
        wait_until(lambda: controller.state == LogLinkState.RECONNECTING)
        assert [entry.text for entry in entries] == [PLAIN]
        assert [state for state, _ in states] == [
            LogLinkState.INACTIVE,
            LogLinkState.CONNECTING,
            LogLinkState.CONNECTED,
            LogLinkState.RECONNECTING,
        ]
        assert states[-1][1] == "reset"

        # WHEN
        controller.set_active(False)

        # THEN
        assert controller.state == LogLinkState.INACTIVE
        wait_until(lambda: _FakeClient.created[0].cancelled)

    def test_another_device_starts_a_new_stream(self, async_loop):
        # GIVEN
        controller, entries, states, changed = self._controller(async_loop)
        controller.set_active(True)
        controller.set_device(_Device("one"))
        wait_until(lambda: _FakeClient.created and _FakeClient.created[0].started)

        # WHEN
        controller.set_device(_Device("two"))

        # THEN
        wait_until(lambda: len(_FakeClient.created) == 2)
        assert [client.device.name for client in _FakeClient.created] == ["one", "two"]
        wait_until(lambda: _FakeClient.created[0].cancelled)
        assert len(changed) == 2

    def test_the_same_device_again_keeps_the_stream(self, async_loop):
        # GIVEN
        controller, _, _, changed = self._controller(async_loop)
        controller.set_active(True)
        controller.set_device(_Device("plate"))
        wait_until(lambda: len(_FakeClient.created) == 1)

        # WHEN: the devices were reloaded
        controller.set_device(_Device("plate"))

        # THEN
        assert len(_FakeClient.created) == 1
        assert len(changed) == 1

    def test_tells_when_the_plate_sends_no_colors(self, async_loop):
        # GIVEN
        lines = [parse_log_line(f"[{i:4}.000][1/2  3][4/5  6] HASP: a") for i in range(10)]
        controller, entries, states, _ = self._controller(async_loop, lines)
        missing = []
        controller.colorsMissingChanged.connect(missing.append)
        controller.set_device(_Device("plate"))

        # WHEN
        controller.set_active(True)

        # THEN
        wait_until(lambda: controller.colors_missing)
        assert missing == [True]

        # WHEN: the stream starts over, with a plate that sends colors
        controller.set_active(False)

        # THEN
        assert missing == [True, False]

    def test_colors_are_not_missing_when_lines_have_them(self, async_loop):
        # GIVEN
        colored = "\x1b[97m[   1.000][1/2  3][4/5  6]\x1b[97m HASP: a"
        controller, entries, *_ = self._controller(async_loop, [parse_log_line(colored) for _ in range(15)])
        controller.set_device(_Device("plate"))

        # WHEN
        controller.set_active(True)

        # THEN
        wait_until(lambda: len(entries) == 15)
        assert not controller.colors_missing

    def test_no_device(self, async_loop):
        # GIVEN
        controller, *_ = self._controller(async_loop)
        controller.set_active(True)
        controller.set_device(_Device("plate"))
        wait_until(lambda: _FakeClient.created and _FakeClient.created[0].started)

        # WHEN
        controller.set_device(None)

        # THEN
        assert controller.state == LogLinkState.NO_DEVICE
        wait_until(lambda: _FakeClient.created[0].cancelled)
