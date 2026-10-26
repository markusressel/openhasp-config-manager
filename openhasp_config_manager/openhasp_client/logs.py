"""
The log of a plate, as the CLI and the GUI show it. Qt-free and independent of the connection: it parses text, and
`follow_logs` turns a connection to the plate's telnet server into a stream of entries that survives connection losses.

The plate writes one line per entry (see `debugPrintPrefix` in the openHASP source):
`[   936.942][65524/77408 15][44476/45088  2] MQTT RCV: p1b2.text=a`, which are the time (of the day, or the seconds since boot while
the clock is not set), the free memory of the heap and of LVGL, the tag of the part of the firmware that logs, and the message.
The telnet server mixes cursor control codes and a prompt (`Prompt > `) into that.

The level of an entry is not part of the line: it is the color of the line, which the plate only sends if `debug.ansi` is on. Without
it, the level is guessed from the tag and the words of the message.
"""

import asyncio
import logging
import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from enum import StrEnum
from typing import AsyncIterator, Awaitable, Callable, List, Optional, Tuple, Union

LOGGER = logging.getLogger(__name__)


class LogLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    TRACE = "trace"
    VERBOSE = "verbose"
    DEBUG = "debug"
    # what the plate publishes to and receives from the MQTT broker
    SENT = "sent"
    RECEIVED = "received"


class Segment(StrEnum):
    """The parts of an entry that are shown in their own style."""

    TIMESTAMP = "timestamp"
    MEMORY = "memory"
    TAG = "tag"
    MESSAGE = "message"


# the colors openHASP gives to the level of a line (`debugPrintPriority` and `debugPrintPrefix`)
_LEVEL_OF_COLOR = {
    "91": LogLevel.ERROR,
    "93": LogLevel.WARNING,
    "97": LogLevel.INFO,
    "37": LogLevel.TRACE,
    "96": LogLevel.VERBOSE,
    "94": LogLevel.DEBUG,
    "92": LogLevel.SENT,
    "38;5;214": LogLevel.RECEIVED,
}
_LEVEL_OF_TAG = {"MQTT PUB": LogLevel.SENT, "MQTT RCV": LogLevel.RECEIVED}
# the messages of these tags repeat what a user or a script sent, so their words say nothing about the plate
_TAGS_WITHOUT_GUESSING = frozenset({"MQTT PUB", "MQTT RCV", "MSGR", "MQTT"})
_ERROR_WORDS = re.compile(
    r"\b(error|errors|fail|fails|failed|failure|fatal|exception|invalid|unable|cannot|could not)\b", re.I
)
_WARNING_WORDS = re.compile(r"\b(warn|warning|timeout|timed out|retry|retrying|lost|disconnected|not found|unknown)\b", re.I)

# a color code right before the tag: `\x1b[91m MQTT: ` (the timestamp has one too, but is followed by `[`)
_COLOR_BEFORE_TAG = re.compile(r"\x1b\[([0-9;]+)m ?(?=[A-Z][A-Z0-9_ ]{0,8}: )")
# any escape sequence of the telnet server: colors, moving the cursor, clearing the line, setting the title
_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
_PROMPT = "Prompt > "
# the time, the two memory blocks (`[free biggest/free total fragmentation]`), the tag and the message
_ENTRY = re.compile(
    r"^(?P<timestamp>\[[\d:.\s-]+\])(?P<memory>(?:\[\s*\d+/[\d\s]+\])*) ?(?:(?P<tag>[A-Z][A-Z0-9_ ]{0,8}): )?(?P<message>.*)$"
)


@dataclass(frozen=True)
class LogEntry:
    """
    One line of the log.

    A line that doesn't start with a time (the plate also prints text that is not from the log, and messages with several lines) is
    a `continuation`, which only has a `message`.
    """

    message: str
    timestamp: str = ""
    memory: str = ""
    tag: str = ""
    level: Optional[LogLevel] = None
    continuation: bool = False
    # whether the plate sent the color of the level (`debug.ansi`), so `level` is exact and not guessed
    colored: bool = False

    @property
    def text(self) -> str:
        """:return: the line as the plate wrote it, without control codes"""
        return "".join(text for _, text in self.segments())

    def segments(self) -> List[Tuple[Segment, str]]:
        """:return: the parts of the line in order, with the separators they are written with, for showing them in styles"""
        result = []
        if self.timestamp:
            result.append((Segment.TIMESTAMP, self.timestamp))
        if self.memory:
            result.append((Segment.MEMORY, self.memory))
        if self.tag:
            result.append((Segment.TAG, f" {self.tag}: "))
        elif self.timestamp:
            result.append((Segment.TAG, " "))
        result.append((Segment.MESSAGE, self.message))
        return result


def guess_level(tag: str, message: str) -> Optional[LogLevel]:
    """:return: the level of a line from its tag and words, if it has none by color. Errors win over warnings."""
    if tag in _LEVEL_OF_TAG:
        return _LEVEL_OF_TAG[tag]
    if tag in _TAGS_WITHOUT_GUESSING:
        return None
    if _ERROR_WORDS.search(message):
        return LogLevel.ERROR
    if _WARNING_WORDS.search(message):
        return LogLevel.WARNING
    return None


def parse_log_line(line: str) -> LogEntry:
    """
    :param line: one line of the telnet server, with its control codes
    :return: the entry. A line that doesn't look like a log entry is a continuation of the one before.
    """
    colors = _COLOR_BEFORE_TAG.findall(line)
    plain = clean_line(line)
    match = _ENTRY.match(plain)
    if match is None:
        return LogEntry(message=plain, continuation=True)
    tag = match["tag"] or ""
    level = _LEVEL_OF_COLOR.get(colors[-1]) if colors else None
    return LogEntry(
        message=match["message"],
        timestamp=match["timestamp"],
        memory=match["memory"],
        tag=tag,
        level=level or guess_level(tag, match["message"]),
        colored=level is not None,
    )


def clean_line(line: str) -> str:
    """:return: the line without control codes and prompts, and without its line ending"""
    return _ESCAPE.sub("", line).replace(_PROMPT, "").rstrip("\r\n").lstrip(" ")


class LogLineAssembler:
    """Turns the chunks the telnet server sends, which end anywhere, into entries."""

    def __init__(self):
        self._buffer = ""

    def feed(self, chunk: str) -> List[LogEntry]:
        """:return: the entries whose line is complete now. The rest of the chunk waits for its end."""
        self._buffer += chunk
        *lines, self._buffer = self._buffer.split("\n")
        entries = []
        for line in lines:
            if clean_line(line):
                entries.append(parse_log_line(line))
        return entries


# --- following a plate ---


@dataclass(frozen=True)
class LogConnectionEvent:
    """The connection to the plate was made (`connected`) or lost."""

    connected: bool
    error: Optional[str] = None


LogItem = Union[LogEntry, LogConnectionEvent]
# a connection to the log of a plate: `async with connect() as chunks:` where `chunks` yields what the plate sends
LogConnector = Callable[[], AbstractAsyncContextManager[AsyncIterator[str]]]

RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 15.0


def describe_error(error: BaseException) -> str:
    return str(error) or type(error).__name__


async def follow_logs(
    connect: LogConnector,
    reconnect: bool = True,
    retry_delay: float = RETRY_DELAY,
    max_retry_delay: float = MAX_RETRY_DELAY,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[LogItem]:
    """
    Streams the entries of a plate's log, forever if it is cancelled (stop iterating) or `reconnect` is set.

    :param connect: opens a connection to the plate, see `LogConnector`
    :param reconnect: connect again after the connection was lost or could not be made, waiting longer (up to `max_retry_delay`)
        for every failure in a row. A `LogConnectionEvent` tells about each change. If not set, the error is raised instead.
    :param sleep: for tests
    """
    delay = retry_delay
    while True:
        error: BaseException
        try:
            async with connect() as chunks:
                yield LogConnectionEvent(connected=True)
                delay = retry_delay
                assembler = LogLineAssembler()
                async for chunk in chunks:
                    for entry in assembler.feed(chunk):
                        yield entry
            error = ConnectionError("The plate closed the connection")
        except Exception as ex:
            error = ex
        if not reconnect:
            raise error
        LOGGER.debug(f"Lost the connection to the log of the plate, trying again in {delay}s: {describe_error(error)}")
        yield LogConnectionEvent(connected=False, error=describe_error(error))
        await sleep(delay)
        delay = min(delay * 2, max_retry_delay)
