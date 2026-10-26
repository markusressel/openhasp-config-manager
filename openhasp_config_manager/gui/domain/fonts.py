"""The fonts of the plate. Qt-free."""

import re


def font_size(value, default: int = 25) -> float:
    """
    :param value: the `text_font` of an object: the size of a built-in font, or the name of a font file, which ends with its size
        (`arial20`, `arial_20`)
    :return: the size, the default if there is none (e.g. a template that is not rendered)
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    match = re.search(r"(\d+)$", value) if isinstance(value, str) else None
    return int(match[1]) if match else default
