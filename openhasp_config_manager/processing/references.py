"""
Finds the files that a `.cmd` or `.jsonl` text refers to. Qt-free and independent of the config directory: it only reads text.

- Images are referenced with a path of the plate's flash: `"src": "L:/home_image.png"`.
- Fonts are referenced by name, without `L:/` and without the extension (https://www.openhasp.com/0.7.0/design/fonts/): the name of
  a `.bin` font file (`"text_font": "arial_20"` is `arial_20.bin`), or the name of a `.ttf` file followed by the size
  (`"text_font": "arial20"` or `"arial_20"` is `arial.ttf` in size 20). A number is a built-in font.
"""

import re
from fnmatch import fnmatchcase
from typing import Iterable, List, Optional, Set

# L:/ followed by a file name of an image, up to the end of the string or the line
_IMAGE = re.compile(r"""L:/([^"'\s,]+?\.(?:png|bin))(?![\w.])""")
# `"text_font": "arial20"` in a JSONL object and `p1b2.text_font=arial20` in a command, with an optional style part and state
_FONT_IN_JSON = re.compile(r"""["']\w*_font\d{0,2}["']\s*:\s*["']([^"']+)["']""")
_FONT_IN_COMMAND = re.compile(r"""\b\w*_font\d{0,2}\s*=\s*["']?([^"'\s]+)""")


def _without_comments(text: str) -> Iterable[str]:
    return (line for line in text.splitlines() if not line.lstrip().startswith("//"))


def find_image_references(text: str) -> Set[str]:
    """:return: the names of the image files (`home_image.png`) that the text refers to as `L:/home_image.png`"""
    return {match for line in _without_comments(text) for match in _IMAGE.findall(line)}


def find_font_references(text: str) -> Set[str]:
    """:return: the values of the font properties in the text that name a font file, not a built-in font (a number)"""
    result = set()
    for line in _without_comments(text):
        for pattern in (_FONT_IN_JSON, _FONT_IN_COMMAND):
            result.update(value for value in pattern.findall(line) if not value.isdigit())
    return result


def font_file_name(reference: str, file_names: Iterable[str]) -> Optional[str]:
    """
    :param reference: the value of a font property, see `find_font_references`
    :param file_names: the names of the files that could be the font, as they are on the plate
    :return: the name of the font file the reference means, if there is one. A `.bin` font wins over a `.ttf` font, like on the plate.
    """
    names = list(file_names)
    if f"{reference}.bin" in names:
        return f"{reference}.bin"
    for name in names:
        # the plate drops an underscore before the size: `arial_20` is `arial.ttf` in size 20 too
        if name.endswith(".ttf") and re.fullmatch(rf"{re.escape(name[:-4])}_?\d+", reference):
            return name
    return None


def matching_names(patterns: Iterable[str], file_names: Iterable[str]) -> List[str]:
    """:return: the names that match one of the glob patterns (`*`, `?`, `[a-z]`) completely"""
    patterns = list(patterns)
    return [name for name in file_names if any(fnmatchcase(name, pattern) for pattern in patterns)]


def use_binary_images(text: str, png_names: Iterable[str]) -> str:
    """:return: the text with the references to the given PNG images (`L:/a.png`) changed to their binary version (`L:/a.bin`)"""
    names = set(png_names)
    return _IMAGE.sub(lambda match: f"L:/{match[1][:-4]}.bin" if match[1] in names else match[0], text)
