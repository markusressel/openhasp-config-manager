import click
import pytest

from openhasp_config_manager.cli import logs
from openhasp_config_manager.cli.logs import c_logs, format_entry, should_color
from openhasp_config_manager.openhasp_client.logs import LogConnectionEvent, parse_log_line
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from tests import TestBase

ERROR_LINE = "[   1.000][1/2  3][4/5  6] FILE: Failed to open"


class TestFormatEntry(TestBase):
    def test_without_color_it_is_the_line_of_the_plate(self):
        assert format_entry(parse_log_line(ERROR_LINE), color=False) == ERROR_LINE

    def test_with_color_the_parts_have_their_own_style(self):
        # WHEN
        text = format_entry(parse_log_line(ERROR_LINE), color=True)

        # THEN
        assert click.unstyle(text) == ERROR_LINE
        assert text.endswith(click.style("Failed to open", fg="red"))
        assert text != ERROR_LINE

    def test_a_line_without_a_level_keeps_its_message_plain(self):
        # WHEN
        text = format_entry(parse_log_line("[   1.000] HASP: Hello"), color=True)

        # THEN
        assert text.endswith("Hello")
        assert not text.endswith("\x1b[0m")


class TestShouldColor(TestBase):
    class _Stream:
        def __init__(self, tty):
            self.tty = tty

        def isatty(self):
            return self.tty

    def test_a_choice_wins(self):
        assert should_color(True, self._Stream(False))
        assert not should_color(False, self._Stream(True))

    def test_only_a_terminal_by_default(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert should_color(None, self._Stream(True))
        assert not should_color(None, self._Stream(False))

    def test_no_color_variable(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        assert not should_color(None, self._Stream(True))


class TestLogsCommand(TestBase):
    def _follow(self, monkeypatch, items=(), error=None, calls=None):
        async def stream(client, reconnect=True):
            if calls is not None:
                calls.append(reconnect)
            for item in items:
                yield item
            if error is not None:
                raise error

        monkeypatch.setattr(OpenHaspClient, "follow_logs", stream)

    async def test_prints_the_log_and_writes_it_to_a_file(self, monkeypatch, capsys, tmp_path):
        # GIVEN
        self._follow(monkeypatch, [LogConnectionEvent(True), parse_log_line(ERROR_LINE), parse_log_line("[   2.000] b")])
        target = tmp_path / "plate.log"
        target.write_text("old\n")

        # WHEN
        await c_logs(self.cfg_root, "test_device", output=target, color=False)

        # THEN
        captured = capsys.readouterr()
        assert captured.out.splitlines()[-2:] == [ERROR_LINE, "[   2.000] b"]
        assert "Connected" in captured.err
        assert target.read_text() == f"old\n{ERROR_LINE}\n[   2.000] b\n"

    async def test_the_status_is_not_part_of_the_output(self, monkeypatch, capsys):
        # GIVEN
        self._follow(monkeypatch, [LogConnectionEvent(True), LogConnectionEvent(False, "reset"), parse_log_line("[   2.000] b")])

        # WHEN
        await c_logs(self.cfg_root, "test_device", color=False)

        # THEN
        captured = capsys.readouterr()
        assert captured.out.splitlines() == ["[   2.000] b"]
        assert "Connection lost, trying again: reset" in captured.err

    async def test_reconnect_is_passed_on(self, monkeypatch):
        # GIVEN
        calls = []
        self._follow(monkeypatch, calls=calls)

        # WHEN
        await c_logs(self.cfg_root, "test_device", reconnect=True)
        await c_logs(self.cfg_root, "test_device")

        # THEN
        assert calls == [True, False]

    async def test_a_lost_connection_fails_the_command(self, monkeypatch, capsys):
        # GIVEN
        self._follow(monkeypatch, error=ConnectionError("The plate closed the connection"))

        # WHEN
        with pytest.raises(click.exceptions.Exit) as exit_info:
            await c_logs(self.cfg_root, "test_device")

        # THEN
        assert exit_info.value.exit_code == 1
        assert "The plate closed the connection" in capsys.readouterr().err

    async def test_no_matching_device(self, capsys):
        # WHEN
        with pytest.raises(click.exceptions.Exit):
            await c_logs(self.cfg_root, "nothing")

        # THEN
        assert "No device matches the filter: nothing" in capsys.readouterr().err
