"""
What the Logs panel shows: the last entries of a plate's log, filtered by a text, and the state of the connection that delivers them.
Qt-free.
"""

from collections import deque
from enum import StrEnum
from typing import Deque, Iterable, List, Optional, Tuple

from openhasp_config_manager.openhasp_client.logs import LogEntry

MAX_ENTRIES = 5000


class LogLinkState(StrEnum):
    NO_DEVICE = "no_device"
    # the panel is hidden, so there is no connection: the plate only allows one telnet connection
    INACTIVE = "inactive"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    # the connection was lost (or could not be made) and is tried again
    RECONNECTING = "reconnecting"


def describe_link(state: LogLinkState, error: Optional[str] = None) -> Tuple[str, str]:
    """:return: the text for the panel's status line, and the style role of the label (hint, error, success)"""
    match state:
        case LogLinkState.NO_DEVICE:
            return "Select a device to see its log.", "hint"
        case LogLinkState.INACTIVE:
            return "Not connected while the panel is hidden.", "hint"
        case LogLinkState.CONNECTING:
            return "Connecting…", "hint"
        case LogLinkState.CONNECTED:
            return "Connected", "success"
        case LogLinkState.RECONNECTING:
            return f"Connection lost, trying again: {error}" if error else "Connection lost, trying again…", "error"
    raise ValueError(state)


def matches(entry: LogEntry, query: str) -> bool:
    """:return: whether the line of the entry contains the text, ignoring case. Every entry matches an empty text."""
    return query.casefold() in entry.text.casefold()


class LogHistory:
    """The newest entries of the log, oldest first. The oldest are dropped when there are more than `capacity`."""

    def __init__(self, capacity: int = MAX_ENTRIES):
        self._entries: Deque[LogEntry] = deque(maxlen=capacity)

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, entries: Iterable[LogEntry]):
        self._entries.extend(entries)

    def clear(self):
        self._entries.clear()

    def filtered(self, query: str = "") -> List[LogEntry]:
        """:return: the entries that contain the text"""
        return [entry for entry in self._entries if matches(entry, query)] if query else list(self._entries)
