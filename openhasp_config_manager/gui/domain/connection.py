import dataclasses
from dataclasses import dataclass
from enum import StrEnum
from typing import FrozenSet, Optional, Tuple


class LinkState(StrEnum):
    NO_DEVICE = "no_device"
    # connecting to the MQTT broker
    CONNECTING = "connecting"
    BROKER_UNREACHABLE = "broker_unreachable"
    # connected to the broker, the plate has not reported its state (LWT) yet
    PLATE_UNKNOWN = "plate_unknown"
    PLATE_ONLINE = "plate_online"
    PLATE_OFFLINE = "plate_offline"


class Severity(StrEnum):
    NEUTRAL = "neutral"
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


_LINK_TEXT = {
    LinkState.NO_DEVICE: ("No device", Severity.NEUTRAL),
    LinkState.CONNECTING: ("Connecting…", Severity.NEUTRAL),
    LinkState.BROKER_UNREACHABLE: ("Broker unreachable", Severity.ERROR),
    LinkState.PLATE_UNKNOWN: ("No status from plate", Severity.WARNING),
    LinkState.PLATE_ONLINE: ("Online", Severity.OK),
    LinkState.PLATE_OFFLINE: ("Plate offline", Severity.ERROR),
}

_SEVERITY_ORDER = [Severity.NEUTRAL, Severity.OK, Severity.WARNING, Severity.ERROR]


@dataclass(frozen=True)
class ConnectionStatus:
    """
    The connection to the selected plate, as shown in the status bar: the link (MQTT broker and the plate's LWT),
    whether something is being sent, and the pages that may show something else on the plate than in the editor
    because sending them failed.
    """

    link: LinkState = LinkState.NO_DEVICE
    error: Optional[str] = None
    sending: bool = False
    out_of_sync_pages: FrozenSet[int] = frozenset()

    @classmethod
    def connecting(cls) -> "ConnectionStatus":
        return cls(link=LinkState.CONNECTING)

    def with_broker(self, connected: bool, error: Optional[str] = None) -> "ConnectionStatus":
        if not connected:
            return dataclasses.replace(self, link=LinkState.BROKER_UNREACHABLE, error=error)
        if self.link in (LinkState.CONNECTING, LinkState.BROKER_UNREACHABLE):
            # the plate's retained LWT follows
            return dataclasses.replace(self, link=LinkState.PLATE_UNKNOWN, error=None)
        return self

    def with_lwt(self, payload: str) -> "ConnectionStatus":
        """
        :param payload: the plate's LWT message: openHASP sends "online", the broker "offline" when the plate disappears
        """
        if payload == "online":
            return dataclasses.replace(self, link=LinkState.PLATE_ONLINE, error=None)
        if payload == "offline":
            return dataclasses.replace(self, link=LinkState.PLATE_OFFLINE, error=None)
        return self

    def with_sending(self, sending: bool) -> "ConnectionStatus":
        return dataclasses.replace(self, sending=sending)

    def with_send_failed(self, page: int) -> "ConnectionStatus":
        return dataclasses.replace(self, out_of_sync_pages=self.out_of_sync_pages | {page})

    def with_page_deployed(self, page: int) -> "ConnectionStatus":
        return dataclasses.replace(self, out_of_sync_pages=self.out_of_sync_pages - {page})

    def with_plate_restored(self) -> "ConnectionStatus":
        """The plate shows its files again (restored or restarted): no page differs from what it should show."""
        return dataclasses.replace(self, out_of_sync_pages=frozenset())

    @property
    def summary(self) -> Tuple[str, Severity]:
        """
        :return: the text for the status bar and how bad it is
        """
        text, severity = _LINK_TEXT[self.link]
        parts = [text]
        if self.sending:
            parts.append("Sending…")
        if self.out_of_sync_pages:
            pages = ", ".join(str(page) for page in sorted(self.out_of_sync_pages))
            parts.append(f"Out of sync (page {pages})")
            severity = max(severity, Severity.WARNING, key=_SEVERITY_ORDER.index)
        return "  ·  ".join(parts), severity

    @property
    def details(self) -> str:
        """
        :return: an explanation for the tooltip
        """
        lines = {
            LinkState.NO_DEVICE: "No device is selected.",
            LinkState.CONNECTING: "Connecting to the MQTT broker of the plate…",
            LinkState.BROKER_UNREACHABLE: f"The MQTT broker can't be reached: {self.error}. Retrying every few seconds.",
            LinkState.PLATE_UNKNOWN: "Connected to the MQTT broker, but the plate has not reported its state (LWT) yet. "
            "It may never have connected to this broker.",
            LinkState.PLATE_ONLINE: "The plate is connected to the MQTT broker.",
            LinkState.PLATE_OFFLINE: "The plate is not connected to the MQTT broker: what is sent now is lost.",
        }
        result = [lines[self.link]]
        if self.out_of_sync_pages:
            result.append(
                "The plate may show something else than it should: sending failed, or a page was cleared. "
                "Click to send the page again (Live preview) or to restore the plate."
            )
        return "\n".join(result)
