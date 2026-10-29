"""
The placeholders openHASP replaces in the text of an object at runtime, like `"text": "%ip%"`, for the text editor. Qt-free.

Ported from `my_label_set_text` in `src/hasp/hasp_attribute_helper.h` of openHASP 0.7.0-rc13 (the hashes are `ATTR_TEXT_MAC`, ...
in `src/hasp/hasp_attribute.h`): a text is replaced only when it is the placeholder and nothing else (`"IP: %ip%"` stays as it
is), the case does not matter (`Parser::get_sdbm` hashes the lower case text), and only the `text` of a `btn`, a `label` and a
`msgbox` is replaced (`attribute_common_text` in `src/hasp/hasp_attribute.cpp`; a `checkbox`, `tabview`, ... shows it as written).
`%ip%` and `%ssid%` are only replaced by firmware with WiFi (`HASP_USE_WIFI`). `%mac%` is not in the documentation of 0.7.0.
The firmware compares a hash of the text (`Parser::get_sdbm`, which skips digits) and its length, see `replaced_placeholder`.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# https://www.openhasp.com/0.7.0/design/data-types/#variables
DOCS_URL = "https://www.openhasp.com/0.7.0/design/data-types/#variables"

# the object types whose `text` is replaced (see the docstring of the module)
REPLACED_IN_TYPES = ("btn", "label", "msgbox")

# the property whose value is replaced
PLACEHOLDER_PROPERTY = "text"


@dataclass(frozen=True)
class Placeholder:
    # as it is written, with its `%`, e.g. `%ip%`
    name: str
    # what openHASP shows instead of it. Parts in `backticks` are code.
    description: str
    # what the preview shows instead of it
    example: str


PLACEHOLDERS: Dict[str, Placeholder] = {
    placeholder.name: placeholder
    for placeholder in (
        Placeholder("%ip%", "The IP address of the plate in its WiFi network, e.g. `192.168.1.42`.", "192.168.1.42"),
        Placeholder("%hostname%", "The hostname (node name) of the plate, as it is set in its configuration.", "plate"),
        Placeholder("%ssid%", "The SSID of the WiFi network the plate is connected to.", "MyWiFi"),
        Placeholder(
            "%model%",
            "The model of the plate, as it is set in the firmware (`HASP_MODEL`, else the name of the build environment).",
            "ESP32-S3",
        ),
        Placeholder("%version%", "The version of the firmware, e.g. `0.7.0-rc13`.", "0.7.0-rc13"),
        Placeholder(
            "%mac%", "The MAC address of the plate (its hardware id), 12 hex digits without separators.", "a1b2c3d4e5f6"
        ),
    )
}

# the start of a placeholder that is being typed: a `%` and letters
_TYPED = re.compile(r"%[A-Za-z]*")
# what looks like a placeholder: letters between two `%`
_LOOKS_LIKE = re.compile(r"%[A-Za-z]+%")


def sdbm(text: str) -> int:
    """:return: the hash the firmware compares names with, a port of `Parser::get_sdbm` in `src/hasp/hasp_parser.cpp`"""
    result = 0
    for byte in text.lower().encode():
        # digits are skipped
        if byte > 57 or byte < 48:
            result = (byte + (result << 6) - result) & 0xFFFF
    return result


_HASHES = {(sdbm(name), len(name)): placeholder for name, placeholder in PLACEHOLDERS.items()}


def replaced_placeholder(text: str) -> Optional[Placeholder]:
    """
    A port of `my_label_set_text` in `src/hasp/hasp_attribute_helper.h`: a text that starts with `%` is replaced when its hash
    and its length (in bytes) are those of a placeholder.
    :return: the placeholder the plate shows instead of the text (of a `btn`, `label` or `msgbox`), None if it shows the text
    """
    return _HASHES.get((sdbm(text), len(text.encode()))) if text.startswith("%") else None


def shown_text(text: Any) -> Any:
    """:return: the text of a `btn`, `label` or `msgbox` as the preview shows it: the example value of a placeholder"""
    found = replaced_placeholder(text) if isinstance(text, str) else None
    return found.example if found else text


def placeholder_problems(obj: Dict) -> List[str]:
    """
    :param obj: a rendered object
    :return: why the plate shows its `text` as written although it looks like a placeholder, empty if it doesn't (only what
        certainly isn't replaced: `%ip%` and `%ssid%` aren't replaced by firmware without WiFi either, which isn't known here)
    """
    text = obj.get(PLACEHOLDER_PROPERTY)
    if not isinstance(text, str) or "{{" in text:
        # a template that can't be rendered is a problem of its own
        return []
    obj_type = obj.get("obj")
    replaced = replaced_placeholder(text)
    if replaced is None and _LOOKS_LIKE.fullmatch(text):
        known = ", ".join(PLACEHOLDERS)
        return [f"{text} is no placeholder of openHASP, the plate shows it as written (the placeholders: {known})"]
    found = [match[0] for match in _LOOKS_LIKE.finditer(text) if match[0].lower() in PLACEHOLDERS]
    if isinstance(obj_type, str) and obj_type.lower() not in REPLACED_IN_TYPES and (replaced or found):
        types = ", ".join(REPLACED_IN_TYPES[:-1]) + f" or {REPLACED_IN_TYPES[-1]}"
        name = replaced.name if replaced else found[0]
        return [f"openHASP replaces {name} only in the text of a {types}, not of a {obj_type}"]
    if replaced is None and found:
        return [f"openHASP replaces {name} only when it is the whole text, the plate shows it as written" for name in found]
    return []


def placeholder_of(value: str) -> Optional[Placeholder]:
    """
    :param value: the text of a string, without its quotes
    :return: the placeholder the text is, None if it is something else (also a text that only contains one)
    """
    return PLACEHOLDERS.get(value.lower())


def placeholder_candidates(prefix: str) -> List[str]:
    """:return: the placeholders that start with what is typed (`%`, `%ho`, ...), in any case, without one typed completely"""
    typed = prefix.lower()
    return sorted(name for name in PLACEHOLDERS if name.startswith(typed) and name != typed)


def typed_placeholder_end(line: str, column: int) -> int:
    """:return: where the rest of the placeholder at a column ends: the letters after it and its closing `%`, if they are there"""
    end = column + len(re.match(r"[A-Za-z]*", line[column:])[0])
    return end + 1 if line[end : end + 1] == "%" else end


def is_typed_placeholder(text: str) -> bool:
    """:return: whether a text is the start of a placeholder, as it is typed: a `%` and letters"""
    return _TYPED.fullmatch(text) is not None
