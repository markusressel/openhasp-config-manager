from openhasp_config_manager.gui.domain.connection import ConnectionStatus, LinkState, Severity
from tests import TestBase


class TestConnectionStatus(TestBase):
    def test_broker_connected_waits_for_the_plate(self):
        # WHEN
        status = ConnectionStatus.connecting().with_broker(True)

        # THEN
        assert status.link == LinkState.PLATE_UNKNOWN
        assert status.summary == ("No status from plate", Severity.WARNING)

    def test_lwt_sets_the_plate_state(self):
        # GIVEN
        status = ConnectionStatus.connecting().with_broker(True)

        # THEN
        assert status.with_lwt("online").summary == ("Online", Severity.OK)
        assert status.with_lwt("offline").summary == ("Plate offline", Severity.ERROR)
        assert status.with_lwt("something else") == status

    def test_reconnecting_to_the_broker_keeps_the_plate_state(self):
        # GIVEN
        status = ConnectionStatus.connecting().with_broker(True).with_lwt("online")

        # THEN
        assert status.with_broker(True).link == LinkState.PLATE_ONLINE

    def test_broker_unreachable(self):
        # WHEN
        status = ConnectionStatus.connecting().with_broker(True).with_lwt("online").with_broker(False, "refused")

        # THEN
        assert status.summary == ("Broker unreachable", Severity.ERROR)
        assert "refused" in status.details

    def test_out_of_sync_pages(self):
        # GIVEN
        status = ConnectionStatus.connecting().with_broker(True).with_lwt("online")

        # WHEN
        status = status.with_send_failed(3).with_send_failed(1).with_sending(True)

        # THEN
        assert status.summary == ("Online  ·  Sending…  ·  Out of sync (page 1, 3)", Severity.WARNING)

        # WHEN
        status = status.with_page_deployed(1).with_page_deployed(3).with_sending(False)

        # THEN
        assert status.summary == ("Online", Severity.OK)

    def test_restoring_the_plate_ends_out_of_sync(self):
        # GIVEN
        status = ConnectionStatus.connecting().with_broker(True).with_lwt("online").with_send_failed(1).with_send_failed(2)

        # WHEN
        status = status.with_plate_restored()

        # THEN
        assert status.summary == ("Online", Severity.OK)

    def test_out_of_sync_does_not_lower_an_error(self):
        # WHEN
        status = ConnectionStatus.connecting().with_broker(False, "refused").with_send_failed(1)

        # THEN
        assert status.summary[1] == Severity.ERROR
