"""
The placeholders openHASP replaces in the text of an object at runtime, like `"text": "%ip%"`, for the text editor. Qt-free.

Ported from `my_label_set_text` in `src/hasp/hasp_attribute_helper.h` of openHASP 0.7.0-rc13 (the hashes are `ATTR_TEXT_MAC`, ...
in `src/hasp/hasp_attribute.h`): a text is replaced only when it is the placeholder and nothing else (`"IP: %ip%"` stays as it
is), the case does not matter (`Parser::get_sdbm` hashes the lower case text), and only the `text` of a `btn`, a `label` and a
`msgbox` is replaced (`attribute_common_text` in `src/hasp/hasp_attribute.cpp`; a `checkbox`, `tabview`, ... shows it as written).
`%ip%` and `%ssid%` are only replaced by firmware with WiFi (`HASP_USE_WIFI`). `%mac%` is not in the documentation of 0.7.0.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

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


PLACEHOLDERS: Dict[str, Placeholder] = {
    placeholder.name: placeholder
    for placeholder in (
        Placeholder("%ip%", "The IP address of the plate in its WiFi network, e.g. `192.168.1.42`."),
        Placeholder("%hostname%", "The hostname (node name) of the plate, as it is set in its configuration."),
        Placeholder("%ssid%", "The SSID of the WiFi network the plate is connected to."),
        Placeholder(
            "%model%",
            "The model of the plate, as it is set in the firmware (`HASP_MODEL`, else the name of the build environment).",
        ),
        Placeholder("%version%", "The version of the firmware, e.g. `0.7.0-rc13`."),
        Placeholder("%mac%", "The MAC address of the plate (its hardware id), 12 hex digits without separators."),
    )
}

# the start of a placeholder that is being typed: a `%` and letters
_TYPED = re.compile(r"%[A-Za-z]*")


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
