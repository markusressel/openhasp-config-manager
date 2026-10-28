"""What the `action` of an object does when it is touched, and what a command moves the plate to. Qt-free."""

import json
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
