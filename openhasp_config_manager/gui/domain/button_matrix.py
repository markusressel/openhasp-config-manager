"""The `options` of a button matrix. Qt-free."""

import json
import re
from dataclasses import dataclass
from typing import List, Optional

# a color for one label: "#FF0000 Red text#"
_COLORED = re.compile(r"^#(?P<color>[0-9a-fA-F]{6}) (?P<text>.*)#$")


@dataclass(frozen=True)
class MatrixButton:
    text: str
    color: Optional[str] = None


def matrix_rows(options) -> List[List[MatrixButton]]:
    """
    :param options: the `options` property: a list of labels (or the same as a JSON text); the label `"\\n"` ends a row
    :return: the buttons by row, leaving out rows without buttons. Anything that is not a list of texts (e.g. a template that
        is not rendered) gives no buttons.
    """
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except ValueError:
            return []
    if not isinstance(options, list):
        return []
    rows: List[List[MatrixButton]] = [[]]
    for label in options:
        if not isinstance(label, str):
            continue
        if label == "\n":
            rows.append([])
            continue
        match = _COLORED.match(label)
        rows[-1].append(MatrixButton(match["text"], f"#{match['color']}") if match else MatrixButton(label))
    return [row for row in rows if row]
