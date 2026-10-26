from openhasp_config_manager.gui.domain.log_history import LogHistory, LogLinkState, describe_link, matches
from openhasp_config_manager.openhasp_client.logs import parse_log_line
from tests import TestBase


def _entry(message: str, tag: str = "HASP"):
    return parse_log_line(f"[   1.000][1/2  3][4/5  6] {tag}: {message}")


class TestLogHistory(TestBase):
    def test_keeps_the_newest_entries(self):
        # GIVEN
        history = LogHistory(capacity=3)

        # WHEN
        history.add(_entry(str(i)) for i in range(5))

        # THEN
        assert [entry.message for entry in history.filtered()] == ["2", "3", "4"]
        assert len(history) == 3

    def test_filters_by_text_ignoring_case(self):
        # GIVEN
        history = LogHistory()
        history.add([_entry("Page changed"), _entry("Connected", tag="MQTT"), _entry("other")])

        # THEN
        assert [entry.message for entry in history.filtered("PAGE")] == ["Page changed"]
        # the tag is part of the line
        assert [entry.message for entry in history.filtered("mqtt")] == ["Connected"]
        assert len(history.filtered("")) == 3
        assert history.filtered("nothing like it") == []

    def test_clear(self):
        # GIVEN
        history = LogHistory()
        history.add([_entry("a")])

        # WHEN
        history.clear()

        # THEN
        assert len(history) == 0

    def test_every_entry_matches_an_empty_text(self):
        assert matches(_entry("a"), "")


class TestDescribeLink(TestBase):
    def test_every_state_has_a_text(self):
        for state in LogLinkState:
            text, role = describe_link(state)
            assert text
            assert role in ("hint", "success", "error")

    def test_a_lost_connection_names_the_error(self):
        assert describe_link(LogLinkState.RECONNECTING, "reset") == ("Connection lost, trying again: reset", "error")
