"""Changes to the text of a device's `config.json` that keep the rest of the file as it is (its order, spacing and comments)."""

import re

_DEBUG_SECTION = re.compile(r'"debug"\s*:\s*\{[^{}]*\}')
_ANSI = re.compile(r'("ansi"\s*:\s*)(?:\d+|true|false)')


def set_debug_ansi(text: str, enabled: bool) -> str:
    """
    :param text: the content of a `config.json`
    :return: the text with `debug.ansi` (the colors of the log lines) set
    :raises ValueError: if the text has no `debug.ansi`
    """
    section = _DEBUG_SECTION.search(text)
    if section is None or _ANSI.search(section[0]) is None:
        raise ValueError('There is no "ansi" setting in the "debug" section')
    changed = _ANSI.sub(lambda match: f"{match[1]}{int(enabled)}", section[0], count=1)
    return text[: section.start()] + changed + text[section.end() :]
