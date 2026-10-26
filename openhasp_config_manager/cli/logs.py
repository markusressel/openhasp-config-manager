import contextlib
import os
import sys
from pathlib import Path
from typing import Optional, TextIO

import click

from openhasp_config_manager.cli.common import _create_config_manager, _analyze_and_filter
from openhasp_config_manager.openhasp_client.logs import LogConnectionEvent, LogEntry, LogLevel, Segment, describe_error
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

_MESSAGE_STYLES = {
    LogLevel.ERROR: {"fg": "red"},
    LogLevel.WARNING: {"fg": "yellow"},
    LogLevel.TRACE: {"fg": "bright_black"},
    LogLevel.VERBOSE: {"fg": "cyan"},
    LogLevel.DEBUG: {"fg": "blue"},
    LogLevel.SENT: {"fg": "green"},
    LogLevel.RECEIVED: {"fg": (255, 175, 0)},
}
_SEGMENT_STYLES = {
    Segment.TIMESTAMP: {"fg": "cyan", "dim": True},
    Segment.MEMORY: {"dim": True},
    Segment.TAG: {"bold": True},
}


def format_entry(entry: LogEntry, color: bool) -> str:
    """:return: the line of the entry, with the colors of the terminal if `color` is set"""
    if not color:
        return entry.text
    parts = []
    for segment, text in entry.segments():
        style = _MESSAGE_STYLES.get(entry.level, {}) if segment == Segment.MESSAGE else _SEGMENT_STYLES.get(segment, {})
        parts.append(click.style(text, **style) if style else text)
    return "".join(parts)


def should_color(color: Optional[bool], stream: TextIO = sys.stdout) -> bool:
    """:param color: what the user asked for, or None to color only a terminal (https://no-color.org)"""
    if color is not None:
        return color
    return stream.isatty() and "NO_COLOR" not in os.environ


def _status(text: str, **style):
    # on stderr, so the output of the command can be piped (`logs | lnav`) or written to a file
    click.echo(click.style(text, **style), err=True)


async def c_logs(
    config_dir: Path,
    device: str,
    output: Optional[Path] = None,
    reconnect: bool = False,
    color: Optional[bool] = None,
):
    """
    Prints the log of a device until it is interrupted.
    :param output: also appends the log (without colors) to this file
    :param reconnect: connect again if the connection is lost
    :param color: use colors, or None for a terminal only
    """
    try:
        # the messages of the analysis are not part of the log
        with contextlib.redirect_stdout(sys.stderr):
            config_manager = _create_config_manager(config_dir, Path("./nonexistent"))
            filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)
        if len(filtered_devices) <= 0:
            raise Exception(f"No device matches the filter: {device}")
        if len(filtered_devices) > 1:
            raise Exception(f"More than one device matches the filter: {device}")
        target = filtered_devices[0]
        use_color = should_color(color)
        _status(f"Listening to the log of '{target.name}'...")
        file = output.open("a", encoding="utf-8") if output is not None else None
        try:
            async for item in OpenHaspClient(target).follow_logs(reconnect=reconnect):
                if isinstance(item, LogConnectionEvent):
                    if item.connected:
                        _status("Connected", fg="green")
                    else:
                        _status(f"Connection lost, trying again: {item.error}", fg="yellow")
                    continue
                click.echo(format_entry(item, use_color))
                if file is not None:
                    file.write(item.text + "\n")
                    file.flush()
        finally:
            if file is not None:
                file.close()
    except BrokenPipeError:
        raise
    except Exception as ex:
        _status(f"{describe_error(ex)}", fg="red")
        raise click.exceptions.Exit(1)
