"""What the `action` of an object does when it is touched, and what a command moves the plate to. Qt-free."""

import json
import re
from dataclasses import dataclass
from typing import List, Mapping, Optional, Union

# the events of an object that an action can name
EVENTS = ("down", "up", "long", "hold", "release", "lost")


def action_commands(action, event: str) -> List[str]:
    """
    :param action: the `action` property of an object: a page (`prev`, `next`, `back`, `p3`, the old way) or the commands per event as
        a JSON object (`{"up": "page 2", "long": ["page 1", "page back"]}`)
    :param event: `down`, `up`, `long`, `hold` or `release`
    :return: the commands the action has for an event, in order
    """
    commands = _events_of(action).get(event)
    if commands is None:
        return []
    return [commands] if isinstance(commands, str) else [command for command in commands if isinstance(command, str)]


def _events_of(action) -> Mapping:
    if isinstance(action, Mapping):
        return action
    text = str(action or "").strip()
    if text.startswith("{"):
        try:
            events = json.loads(text)
        except ValueError:
            return {}  # the plate warns about the parameter and ignores it
        return events if isinstance(events, dict) else {}
    # the old way: a page the button leads to when it is released
    if text.lower() in ("prev", "next", "back"):
        return {"up": f"page {text.lower()}"}
    if len(text) > 1 and text[0] == "p" and text[1:].isdigit():
        return {"up": f"page {int(text[1:])}"}
    return {}


def page_command(command: str) -> Optional[Union[str, int]]:
    """:return: where a command sends the plate: `next`, `prev`, `back` or a page number, None if it is another command"""
    words = command.split()
    if len(words) != 2 or words[0].lower() != "page":
        return None
    target = words[1].lower()
    if target in ("next", "prev", "back"):
        return target
    return int(target) if target.isdigit() else None


@dataclass(frozen=True)
class ObjectCommand:
    """A command that sets a property of an object, e.g. `p1b2.val 1`."""

    page: int
    id: int
    attribute: str
    value: Union[int, str]


# `dispatch_parse_button_attribute`: `p`, the page, an optional `.`, `b`, the id, `.` and the attribute (brackets are optional as well)
_OBJECT_TOPIC = re.compile(r"[pP]\[?(\d+)]?\.?[bB]\[?(\d+)]?\.(\S+)")


def object_command(command: str) -> Optional[ObjectCommand]:
    """
    Like `dispatch_simple_text_command` of the firmware: the topic ends at the first `=` or space, the rest is the value. It sets the
    property if there was a `=` or a value (else it only asks for it).
    :return: the property the command sets, None if it is another command or only asks
    """
    text = command.lstrip(" \t")
    positions = [position for position in (text.find("="), text.find(" ")) if position >= 0]
    if not positions:
        return None
    position = min(positions)
    topic, value = text[:position], text[position + 1 :]
    if text[position] != "=" and not value:
        return None
    match = _OBJECT_TOPIC.fullmatch(topic)
    if match is None:
        return None
    return ObjectCommand(
        page=int(match.group(1)),
        id=int(match.group(2)),
        attribute=match.group(3).lower(),
        value=int(value) if re.fullmatch(r"-?\d+", value.strip()) else value,
    )
