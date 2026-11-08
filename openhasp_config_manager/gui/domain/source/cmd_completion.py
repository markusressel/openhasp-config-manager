"""
What can be completed in a .cmd file: the commands of openHASP at the start of a line (`backlight`, `page`, ...), their arguments
that are one of a few words (`idle off`, `service start http`), the file of a `run` (`run L:/pages.jsonl`), the properties and
methods of an object (`p1b2.text=`, `p1b2.clear`) and their values, and the object of a `jsonl` command like in a .jsonl file.
The type of an object (its `obj`) is taken from the objects of the device (`object_types`), so it gets the properties, methods
and values of its type. Qt-free.

The commands follow the documentation of openHASP 0.7.0: https://www.openhasp.com/0.7.0/commands/ and the methods of
https://www.openhasp.com/0.7.0/design/objects/. Not listed: `output[x]` and `input[x]` (a GPIO number in the name).
"""

import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from openhasp_config_manager.gui.domain.source.completion import (
    CompletionContext,
    Insertion,
    completion_context,
    properties_for,
    value_choice,
    value_words,
)
from openhasp_config_manager.gui.domain.source.docs import PropertyHelp, object_type_at_line, property_help
from openhasp_config_manager.gui.domain.source.objects import SourceObject, scan_objects
from openhasp_config_manager.gui.domain.source.syntax import Language

COMMANDS_URL = "https://www.openhasp.com/0.7.0/commands/"
OBJECTS_URL = "https://www.openhasp.com/0.7.0/design/objects/"

# words with their meaning
Words = Tuple[Tuple[str, str], ...]


@dataclass(frozen=True)
class Command:
    name: str
    # what the command does. Parts in `backticks` are code.
    summary: str
    # the words its argument can be, with their meaning (empty if it takes none or anything)
    arguments: Words = ()
    # whether it takes an argument at all, so a space follows its name when it is chosen
    takes_argument: bool = False
    # the words of a second argument, after any of `arguments` (`http` of `service start http`)
    then: Words = ()


_ON_OFF = (("on", "turn on"), ("off", "turn off"))

COMMANDS = {
    command.name: command
    for command in (
        Command(
            "antiburn",
            "Cycles the screen through black, red, green, blue and white for up to 30 seconds, against burn-in. A touch or "
            "`antiburn off` stops it.",
            _ON_OFF,
            True,
        ),
        Command(
            "backlight",
            'Turns the backlight on or off or sets its brightness (1-255): `backlight off`, `backlight 200`, `backlight {"state":'
            '"on","brightness":128}`.',
            _ON_OFF,
            True,
        ),
        Command("calibrate", "Starts the calibration of the touch screen. A soft reboot saves it."),
        Command(
            "clearpage",
            "Deletes the objects of a page (0-12): `clearpage 2`, of the current page without a number, of every page with "
            "`clearpage all`.",
            (("all", "every page"),),
            True,
        ),
        *(
            Command(
                f"config/{name}",
                f"Changes the {what} settings with a JSON object (`config/{name} {example}`); without one, reports them.",
                (),
                True,
            )
            for name, what, example in (
                ("wifi", "WiFi", '{"ssid":"..."}'),
                ("mqtt", "MQTT", '{"port":1883}'),
                ("http", "web interface", '{"user":"..."}'),
                ("mdns", "mDNS", '{"enable":1}'),
                ("hasp", "HASP", '{"startdim":255}'),
                ("gui", "GUI", '{"idle2":0}'),
                ("debug", "debug", '{"tele":300}'),
                ("gpio", "GPIO", '{"config":[...]}'),
            )
        ),
        Command("discovery", "Sends the discovery message of the plate."),
        Command("factoryreset", "Erases the file system and the settings of the plate and restarts it, without asking."),
        Command(
            "idle",
            "Sets the idle state of the screen. Without an argument, reports it.",
            (
                ("off", "resets the idle time, as if the screen was touched"),
                ("short", "as if the first idle time (`idle1`) was over"),
                ("long", "as if the second idle time (`idle2`) was over"),
            ),
            True,
        ),
        Command("json", 'Runs a list of commands: `json ["page 2","idle off"]`.', (), True),
        Command(
            "jsonl", 'Creates or changes objects: `jsonl {"page":1,"id":2,"obj":"btn","text":"Hi"}` (at most 2 kB).', (), True
        ),
        Command(
            "moodlight",
            'Turns the mood light (an RGB LED) on or off or sets its color: `moodlight {"state":"on","color":"red"}`. Without an '
            "argument, reports it.",
            _ON_OFF,
            True,
        ),
        Command(
            "page",
            "Shows a page (1-12): `page 2`, the next or previous one, or the one shown before. Without an argument, reports it.",
            (("next", "the next page"), ("prev", "the previous page"), ("back", "the page shown before")),
            True,
        ),
        Command("reboot", "Saves the changed settings and restarts the plate."),
        Command("restart", "Saves the changed settings and restarts the plate, like `reboot`."),
        Command(
            "run", "Runs the commands of a .cmd file or creates the objects of a .jsonl file: `run L:/pages.jsonl`.", (), True
        ),
        Command("screenshot", "Saves a picture of the screen as a BMP file, to download at `http://<ip>/screenshot.bmp`."),
        Command("sensors", "Sends the values of the sensors."),
        Command(
            "service",
            "Starts or stops a service of the plate: `service stop http`.",
            (("start", "start the service"), ("stop", "stop the service")),
            True,
            (("http", "the web interface"), ("telnet", "the console over telnet"), ("console", "the serial console")),
        ),
        Command("statusupdate", "Sends the status of the plate (version, uptime, free memory, page, ...)."),
        Command("unzip", "Unpacks an uncompressed zip file of the plate: `unzip L:/icons.zip`.", (), True),
        Command(
            "update", "Updates the firmware from a URL (`update http://.../firmware.bin`) and restarts on success.", (), True
        ),
    )
}

# what an object can be told to do besides setting a property (`p1b2.clear`)
OBJECT_METHODS = {
    "clear": "Deletes the children of the object.",
    "delete": "Deletes the object and its children.",
    "to_front": "Brings the object to the front.",
    "to_back": "Sends the object to the back.",
}
# the methods of some types only
TYPE_METHODS = {
    "dropdown": {"open": "Opens the list of the dropdown.", "close": "Closes the list of the dropdown."},
}

# the kinds of `CompletionContext` of a .cmd file (the ones of the object of a `jsonl` command are those of a .jsonl file)
# "command": the command at the start of a line, "argument": an argument of a command (`key` is the command), "file": the file of a
# `run`, "member": a property or method of an object, "member_value": the value of a property of an object (`key` is the property)
CMD_KINDS = ("command", "argument", "file", "member", "member_value")

_WORD = re.compile(r"[A-Za-z0-9_/.:-]*")
_COMMAND = re.compile(r"^\s*(?P<prefix>[A-Za-z0-9_/]*)$")
_MEMBER = re.compile(r"^\s*(?P<target>p\d+b\d+)\.(?P<prefix>[A-Za-z0-9_]*)$")
_MEMBER_VALUE = re.compile(r"^\s*(?P<target>p\d+b\d+)\.(?P<key>[A-Za-z0-9_]+)\s*(?:=\s*|\s+)(?P<prefix>[A-Za-z0-9_-]*)$")
_RUN = re.compile(r"^\s*run\s+(?P<prefix>\S*)$")
_ARGUMENT = re.compile(r"^\s*(?P<key>[a-z/]+)\s*(?:=\s*|\s+)(?:(?P<target>[a-z]+)\s+)?(?P<prefix>[A-Za-z0-9_-]*)$")
_JSONL = re.compile(r"^\s*jsonl\s+")


def object_types(files: Iterable[Iterable[Dict]]) -> Dict[str, str]:
    """
    :param files: the rendered objects of a device, a list per file in the order of the file
    :return: the type (`obj`) of each object by its name (`p1b2`). An object without a page is on the page of the object before it.
    """
    types = {}
    for objects in files:
        page = None
        for obj in objects:
            page = obj.get("page", page)
            if isinstance(obj.get("obj"), str) and page is not None and "id" in obj:
                types[f"p{page}b{obj['id']}"] = obj["obj"]
    return types


def methods_of(object_type: Optional[str]) -> Dict[str, str]:
    """:return: the methods of an object type with their meaning; of every type if it is not known"""
    if object_type is None:
        return {**OBJECT_METHODS, **{name: text for methods in TYPE_METHODS.values() for name, text in methods.items()}}
    return {**OBJECT_METHODS, **TYPE_METHODS.get(object_type, {})}


def jsonl_start(line: str) -> Optional[int]:
    """:return: where the object of a `jsonl` command starts in a line, None if the line is no `jsonl` command"""
    match = _JSONL.match(line)
    return match.end() if match else None


def jsonl_object(line: str) -> Optional[SourceObject]:
    """:return: the object of a `jsonl` command, None if the line is none or has no object yet"""
    start = jsonl_start(line)
    if start is None:
        return None
    objects = scan_objects(line[start:])
    return objects[0] if objects else None


def jsonl_object_type(found: SourceObject, types: Dict[str, str]) -> Optional[str]:
    """
    :param types: the types of the objects of the device (`object_types`)
    :return: the type of the object of a `jsonl` command: its `obj`, else the type of the object it changes (its `page` and `id`)
    """
    written = object_type_at_line([found], found.start_line)
    if written is not None:
        return written
    page, object_id = found.get("page"), found.get("id")
    if page is None or object_id is None or page.value is None or object_id.value is None:
        return None
    return types.get(f"p{page.value.strip()}b{object_id.value.strip()}")


def cmd_context(line_before_cursor: str) -> Optional[CompletionContext]:
    """:return: what the text before the cursor in a line of a .cmd file asks to complete, None if nothing"""
    line = line_before_cursor
    if (start := jsonl_start(line)) is not None:
        argument = line[start:]
        context = completion_context(argument, Language.JSONL, inside_object="{" in argument)
        # an object sent to the plate can't include anything, only the files of the config can
        if context is None or context.kind == "include":
            return None
        return CompletionContext(context.kind, context.prefix, context.start + start, context.quoted, context.key)
    if match := _COMMAND.match(line):
        return CompletionContext("command", match["prefix"], match.start("prefix"))
    if match := _MEMBER.match(line):
        return CompletionContext("member", match["prefix"], match.start("prefix"), target=match["target"])
    if match := _MEMBER_VALUE.match(line):
        return CompletionContext(
            "member_value", match["prefix"], match.start("prefix"), key=match["key"], target=match["target"]
        )
    if match := _RUN.match(line):
        return CompletionContext("file", match["prefix"], match.start("prefix"))
    if (match := _ARGUMENT.match(line)) and (command := COMMANDS.get(match["key"])) is not None:
        target = match["target"]
        if (command.arguments and target is None) or (command.then and target in dict(command.arguments)):
            return CompletionContext("argument", match["prefix"], match.start("prefix"), key=match["key"], target=target)
    return None


def _argument_words(context: CompletionContext) -> Words:
    command = COMMANDS[context.key]
    return command.arguments if context.target is None else command.then


def cmd_words(
    context: CompletionContext, run_targets: Callable[[], Iterable[str]] = lambda: (), object_type: Optional[str] = None
) -> List[str]:
    """
    :param run_targets: the names of the files the plate has (`pages.jsonl`), asked only for the file of a `run`
    :param object_type: the type of the object of the line (see `object_types`), None if it is not known
    :return: what can be written for a context of `CMD_KINDS`, that starts with the typed prefix (case does not matter)
    """
    if context.kind == "command":
        words = sorted(COMMANDS)
    elif context.kind == "argument":
        words = [word for word, _ in _argument_words(context)]
    elif context.kind == "file":
        words = sorted({f"L:/{name}" for name in run_targets()})
    elif context.kind == "member":
        words = sorted({*properties_for(object_type, context.prefix), *methods_of(object_type)})
    elif context.kind == "member_value":
        words = value_words(object_type, context.key)
    else:
        raise ValueError(f"not a context of a .cmd file: {context.kind}")
    prefix = context.prefix.lower()
    return [word for word in words if word.lower().startswith(prefix) and word != context.prefix]


def cmd_insertion(
    line: str, column: int, context: CompletionContext, word: str, object_type: Optional[str] = None
) -> Insertion:
    """
    What to write when a word is chosen from the list: it replaces what is typed of it, also after the cursor. A command or an
    argument that takes another argument gets a space after it, a property of an object a `=`, unless the line has them already.
    """
    end = column + len(_WORD.match(line, column)[0])
    rest = line[end:]
    text = word
    if _takes_more(context, word) and not rest.startswith((" ", "=")):
        text += " "
    elif context.kind == "member" and word not in methods_of(object_type) and not rest.lstrip().startswith("="):
        text += "="
    return Insertion(context.start, end, text, context.start + len(text))


def _takes_more(context: CompletionContext, word: str) -> bool:
    if context.kind == "command":
        return COMMANDS[word].takes_argument
    return context.kind == "argument" and context.target is None and bool(COMMANDS[context.key].then)


def continues(context: CompletionContext, word: str, object_type: Optional[str] = None) -> bool:
    """:return: whether the list should show again after a word was chosen, for what follows it (the file of a `run`, ...)"""
    if context.kind == "command":
        return word == "run" or bool(COMMANDS[word].arguments)
    if context.kind == "argument":
        return _takes_more(context, word)
    if context.kind == "member":
        return word not in methods_of(object_type) and bool(value_words(object_type, word))
    return False


def cmd_help(context: CompletionContext, word: str, object_type: Optional[str] = None) -> Optional[PropertyHelp]:
    """:return: what a word of the list means, for the card next to it"""
    if context.kind == "command" and word in COMMANDS:
        return PropertyHelp(word, COMMANDS[word].summary, "Command", url=COMMANDS_URL)
    if context.kind == "argument":
        meaning = dict(_argument_words(context)).get(word)
        return None if meaning is None else PropertyHelp(word, meaning, f"Argument of `{context.key}`", url=COMMANDS_URL)
    if context.kind == "member":
        methods = methods_of(object_type)
        if word in methods:
            owner = (
                "an object" if word in OBJECT_METHODS else next(f"a `{t}`" for t, own in TYPE_METHODS.items() if word in own)
            )
            return PropertyHelp(word, methods[word], f"Method of {owner}", url=OBJECTS_URL)
        return property_help(word, object_type)
    if context.kind == "member_value" and (choice := value_choice(object_type, context.key, word)) is not None:
        return PropertyHelp(word, choice.meaning, f"Value of `{context.key}`")
    return None
