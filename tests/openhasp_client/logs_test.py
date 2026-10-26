from contextlib import asynccontextmanager

import pytest

from openhasp_config_manager.openhasp_client import telnet_client
from openhasp_config_manager.openhasp_client.logs import (
    LogConnectionEvent,
    LogEntry,
    LogLevel,
    LogLineAssembler,
    Segment,
    follow_logs,
    guess_level,
    parse_log_line,
)
from openhasp_config_manager.openhasp_client.telnet_client import OpenHaspTelnetClient
from tests import TestBase

PROMPT = "\x1b[1000D\x1b[0KPrompt > \x1b[1000D\x1b[9C"


class TestParseLogLine(TestBase):
    def test_splits_a_line_of_the_plate(self):
        # WHEN
        entry = parse_log_line("[    936.961][61428/81264 24][44476/45088  2] MQTT RCV:  = p2b30.text=-\r\n")

        # THEN
        assert entry == LogEntry(
            message=" = p2b30.text=-",
            timestamp="[    936.961]",
            memory="[61428/81264 24][44476/45088  2]",
            tag="MQTT RCV",
            level=LogLevel.RECEIVED,
        )
        assert entry.text == "[    936.961][61428/81264 24][44476/45088  2] MQTT RCV:  = p2b30.text=-"

    def test_a_time_of_the_day(self):
        # WHEN
        entry = parse_log_line("[12:34:56.789][1000/2000  1][100/200  1] HASP: Hello")

        # THEN
        assert (entry.timestamp, entry.tag, entry.message) == ("[12:34:56.789]", "HASP", "Hello")

    def test_removes_the_prompt_and_control_codes_around_a_line(self):
        # WHEN
        entry = parse_log_line(f"{PROMPT}{PROMPT}[     1.000][1/2  3][4/5  6] TELN: Client login\r\n")

        # THEN
        assert entry.text == "[     1.000][1/2  3][4/5  6] TELN: Client login"

    def test_a_line_without_a_time_continues_the_line_before(self):
        # WHEN
        entry = parse_log_line('  {"a": 1}\r\n')

        # THEN
        assert entry == LogEntry(message='{"a": 1}', continuation=True)
        assert entry.segments() == [(Segment.MESSAGE, '{"a": 1}')]

    def test_a_message_in_brackets_is_not_taken_for_a_memory_block(self):
        # WHEN
        entry = parse_log_line("[   1.000][1/2  3][4/5  6] LVGL: [Warn] something")

        # THEN
        assert entry.memory == "[1/2  3][4/5  6]"
        assert entry.message == "[Warn] something"

    def test_a_line_without_memory_or_tag(self):
        # WHEN
        entry = parse_log_line("[   1.000] just text")

        # THEN
        assert (entry.timestamp, entry.memory, entry.tag, entry.message) == ("[   1.000]", "", "", "just text")
        assert entry.text == "[   1.000] just text"

    @pytest.mark.parametrize(
        "color, level",
        [
            ("\x1b[91m", LogLevel.ERROR),
            ("\x1b[93m", LogLevel.WARNING),
            ("\x1b[97m", LogLevel.INFO),
            ("\x1b[37m", LogLevel.TRACE),
            ("\x1b[96m", LogLevel.VERBOSE),
            ("\x1b[94m", LogLevel.DEBUG),
            ("\x1b[92m", LogLevel.SENT),
            ("\x1b[38;5;214m", LogLevel.RECEIVED),
        ],
    )
    def test_the_level_is_the_color_before_the_tag(self, color, level):
        # WHEN
        entry = parse_log_line(f"\x1b[1000D\x1b[0K\x1b[96m[   1.000]\x1b[32m[1/2  3][4/5  6]{color} HASP: all fine\x1b[0m\r\n")

        # THEN
        assert entry.level == level
        assert entry.text == "[   1.000][1/2  3][4/5  6] HASP: all fine"

    def test_the_color_of_the_time_is_not_a_level(self):
        # WHEN
        entry = parse_log_line("\x1b[96m[   1.000]\x1b[0m just text")

        # THEN
        assert entry.level is None


class TestGuessLevel(TestBase):
    def test_words_of_a_message(self):
        assert guess_level("FILE", "Failed to open file") == LogLevel.ERROR
        assert guess_level("WIFI", "Connection timeout") == LogLevel.WARNING
        assert guess_level("HASP", "Page changed") is None

    def test_errors_win_over_warnings(self):
        assert guess_level("HASP", "unknown value, failed") == LogLevel.ERROR

    def test_mqtt_tags_have_their_own_level(self):
        assert guess_level("MQTT PUB", "failed") == LogLevel.SENT
        assert guess_level("MQTT RCV", "failed") == LogLevel.RECEIVED

    def test_the_messages_of_a_command_are_not_guessed(self):
        assert guess_level("MSGR", "p1b1.text=Failed") is None

    def test_guessed_when_the_plate_sends_no_colors(self):
        # WHEN
        entry = parse_log_line("[   1.000][1/2  3][4/5  6] FILE: Failed to open /x")

        # THEN
        assert entry.level == LogLevel.ERROR

    def test_the_color_wins_over_the_words(self):
        # WHEN
        entry = parse_log_line("[   1.000][1/2  3][4/5  6]\x1b[97m FILE: Failed to open /x")

        # THEN
        assert entry.level == LogLevel.INFO


class TestLogLineAssembler(TestBase):
    def test_waits_for_the_end_of_a_line(self):
        # GIVEN
        assembler = LogLineAssembler()

        # WHEN
        first = assembler.feed("[   1.000][1/2  3][4/5  6] HASP: Hel")
        second = assembler.feed("lo\r\n[   2.000][1/2  3][4/5  6] HASP: Wor")
        third = assembler.feed("ld\r\n")

        # THEN
        assert first == []
        assert [entry.message for entry in second] == ["Hello"]
        assert [entry.message for entry in third] == ["World"]

    def test_a_control_code_split_between_two_chunks(self):
        # GIVEN
        assembler = LogLineAssembler()

        # WHEN
        entries = assembler.feed("\x1b[10") + assembler.feed("00D\x1b[0K[   1.000] HASP: x\r\n")

        # THEN
        assert [entry.text for entry in entries] == ["[   1.000] HASP: x"]

    def test_drops_the_lines_that_only_hold_the_prompt(self):
        # GIVEN
        assembler = LogLineAssembler()

        # WHEN
        entries = assembler.feed(f"{PROMPT}\r\n\r\n[   1.000] a\r\n{PROMPT}[   2.000] b\r\n")

        # THEN
        assert [entry.message for entry in entries] == ["a", "b"]

    def test_the_prompt_after_a_line_does_not_end_up_in_the_next_one(self):
        # GIVEN
        assembler = LogLineAssembler()

        # WHEN
        entries = assembler.feed(f"[   1.000] a\r\n{PROMPT}[   2.000] b\r\n{PROMPT}")

        # THEN
        assert [entry.text for entry in entries] == ["[   1.000] a", "[   2.000] b"]


class _Connection:
    """A connection to the log that sends the given chunks, then fails with `error` or, without one, closes."""

    def __init__(self, chunks, error=None, on_open=None):
        self.chunks = chunks
        self.error = error
        self.on_open = on_open
        self.closed = False

    @asynccontextmanager
    async def __call__(self):
        if self.on_open is not None:
            self.on_open()
        try:
            yield self._chunks()
        finally:
            self.closed = True

    async def _chunks(self):
        for chunk in self.chunks:
            yield chunk
        if self.error is not None:
            raise self.error


def _connector(*connections):
    remaining = list(connections)

    def connect():
        connection = remaining.pop(0)
        return connection()

    return connect


async def _collect(stream, limit):
    items = []
    async for item in stream:
        items.append(item)
        if len(items) == limit:
            break
    return items


class TestFollowLogs(TestBase):
    async def test_streams_the_entries_of_the_chunks(self):
        # GIVEN
        connection = _Connection(["[   1.000] a\r\n[   2.0", "00] b\r\n"])

        # WHEN
        items = await _collect(follow_logs(_connector(connection), reconnect=False), 3)

        # THEN
        assert items[0] == LogConnectionEvent(connected=True)
        assert [item.message for item in items[1:]] == ["a", "b"]

    async def test_without_reconnect_a_closed_connection_is_an_error(self):
        # GIVEN
        connection = _Connection(["[   1.000] a\r\n"])
        stream = follow_logs(_connector(connection), reconnect=False)

        # WHEN
        with pytest.raises(ConnectionError, match="closed the connection"):
            async for _ in stream:
                pass

        # THEN
        assert connection.closed

    async def test_without_reconnect_the_error_of_the_connection_is_raised(self):
        # GIVEN
        stream = follow_logs(_connector(_Connection([], error=ConnectionResetError("reset"))), reconnect=False)

        # WHEN / THEN
        with pytest.raises(ConnectionResetError):
            async for _ in stream:
                pass

    async def test_connects_again_after_the_connection_was_lost(self):
        # GIVEN
        connector = _connector(
            _Connection(["[   1.000] a\r\n"], error=ConnectionResetError("reset by peer")),
            _Connection(["[   2.000] b\r\n"]),
        )
        delays = []

        async def sleep(delay):
            delays.append(delay)

        # WHEN
        items = await _collect(follow_logs(connector, reconnect=True, sleep=sleep), 6)

        # THEN
        assert items == [
            LogConnectionEvent(connected=True),
            parse_log_line("[   1.000] a"),
            LogConnectionEvent(connected=False, error="reset by peer"),
            LogConnectionEvent(connected=True),
            parse_log_line("[   2.000] b"),
            LogConnectionEvent(connected=False, error="The plate closed the connection"),
        ]
        assert delays == [1.0]

    async def test_waits_longer_for_every_failed_attempt_and_starts_over_after_a_connection(self):
        # GIVEN
        def refuse():
            raise ConnectionRefusedError("refused")

        connector = _connector(
            _Connection([], on_open=refuse),
            _Connection([], on_open=refuse),
            _Connection([], on_open=refuse),
            _Connection(["[   1.000] a\r\n"]),
            _Connection([], on_open=refuse),
        )
        delays = []

        async def sleep(delay):
            delays.append(delay)

        # WHEN
        items = await _collect(follow_logs(connector, retry_delay=1, max_retry_delay=3, sleep=sleep), 7)

        # THEN
        assert [item.error for item in items if isinstance(item, LogConnectionEvent) and not item.connected] == [
            "refused",
            "refused",
            "refused",
            "The plate closed the connection",
            "refused",
        ]
        assert delays == [1, 2, 3, 1]

    async def test_a_timeout_without_a_message_is_named(self):
        # GIVEN
        def timeout():
            raise TimeoutError()

        connector = _connector(_Connection([], on_open=timeout))

        async def sleep(delay):
            pass

        # WHEN
        items = await _collect(follow_logs(connector, sleep=sleep), 1)

        # THEN
        assert items == [LogConnectionEvent(connected=False, error="TimeoutError")]


class _FakeReader:
    def __init__(self, *chunks):
        self.chunks = list(chunks)

    async def read(self, n):
        return self.chunks.pop(0) if self.chunks else ""


class _FakeWriter:
    def __init__(self):
        self.written = []
        self.closed = False

    def write(self, text):
        self.written.append(text)

    def close(self):
        self.closed = True

    def get_extra_info(self, name):
        return None


class TestTelnetLogin(TestBase):
    def _client(self, reader, writer, monkeypatch):
        async def open_connection(**kwargs):
            return reader, writer

        monkeypatch.setattr(telnet_client, "open_connection", open_connection)
        return OpenHaspTelnetClient("plate", user="admin", password="secret")

    async def test_logs_in_and_hands_over_what_follows_the_prompt(self, monkeypatch):
        # GIVEN
        reader = _FakeReader(
            "Welcome\r\nUsername: ",
            "\x1b[0K#admin",
            "Password: ",
            "\x1b[0K#######\r\n\r\n        Open Hardware edition v0.7.0\r\n\r\nPrompt > [   1.000] HASP: first\r\n",
            "[   2.000] HASP: second\r\n",
        )
        writer = _FakeWriter()
        client = self._client(reader, writer, monkeypatch)

        # WHEN
        async with client.log_connection() as chunks:
            received = [chunk async for chunk in chunks]

        # THEN
        assert writer.written == ["admin\r\n", "secret\r\n"]
        assert received == [" [   1.000] HASP: first\r\n", "[   2.000] HASP: second\r\n"]
        assert writer.closed

    async def test_a_plate_without_a_login(self, monkeypatch):
        # GIVEN
        reader = _FakeReader("\x1b[0KPrompt > ", "[   1.000] HASP: first\r\n")
        writer = _FakeWriter()
        client = self._client(reader, writer, monkeypatch)

        # WHEN
        async with client.log_connection() as chunks:
            received = [chunk async for chunk in chunks]

        # THEN
        assert writer.written == []
        assert "".join(received).lstrip() == "[   1.000] HASP: first\r\n"

    async def test_a_rejected_login(self, monkeypatch):
        # GIVEN
        reader = _FakeReader("Username: ", "Password: ", "Login failed\r\nUsername: ")
        writer = _FakeWriter()
        client = self._client(reader, writer, monkeypatch)

        # WHEN / THEN
        with pytest.raises(PermissionError):
            async with client.log_connection():
                pass
        assert writer.closed

    async def test_the_plate_closes_the_connection_while_logging_in(self, monkeypatch):
        # GIVEN
        client = self._client(_FakeReader("Username: "), _FakeWriter(), monkeypatch)

        # WHEN / THEN
        with pytest.raises(ConnectionError):
            async with client.log_connection():
                pass
