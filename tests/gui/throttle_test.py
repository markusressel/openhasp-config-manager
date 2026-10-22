import pytest

from tests import TestBase


@pytest.mark.usefixtures("qapp")
class TestLatestValueThrottle(TestBase):
    def _throttle(self, sent):
        from openhasp_config_manager.gui.qt.throttle import LatestValueThrottle

        return LatestValueThrottle(sent.append, interval_ms=20)

    def _wait(self, ms: int):
        from PyQt6.QtTest import QTest

        QTest.qWait(ms)

    def test_first_value_is_sent_right_away(self):
        # GIVEN
        sent = []
        throttle = self._throttle(sent)

        # WHEN
        throttle.push(1)

        # THEN
        assert sent == [1]

    def test_values_in_between_are_dropped_and_the_last_is_sent(self):
        # GIVEN
        sent = []
        throttle = self._throttle(sent)

        # WHEN
        for value in range(1, 6):
            throttle.push(value)
        self._wait(100)

        # THEN
        assert sent == [1, 5]

    def test_nothing_more_is_sent_without_new_values(self):
        # GIVEN
        sent = []
        throttle = self._throttle(sent)
        throttle.push(1)

        # WHEN
        self._wait(100)
        throttle.push(2)

        # THEN
        assert sent == [1, 2]

    def test_cancel_drops_the_pending_value(self):
        # GIVEN
        sent = []
        throttle = self._throttle(sent)
        throttle.push(1)
        throttle.push(2)

        # WHEN
        throttle.cancel()
        self._wait(100)

        # THEN
        assert sent == [1]
