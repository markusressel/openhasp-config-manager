"""
What the list of usages of a variable shows: the usages grouped by file, and for each a few lines of code around it. Qt-free.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from openhasp_config_manager.gui.domain.variables.usages import Usage


@dataclass(frozen=True)
class UsagePreview:
    """The lines around a usage, without the indentation they all share."""

    # the number of the first line (starting at 1)
    first_line: int
    lines: List[str]
    # the index of the line of the usage in `lines`
    index: int
    # where the usage is in that line
    column: int
    length: int


def group_by_file(usages: List[Usage]) -> Dict[Path, List[Usage]]:
    """:return: the usages by file, in the order of the usages (files in the order of their first usage)"""
    grouped: Dict[Path, List[Usage]] = {}
    for usage in usages:
        grouped.setdefault(usage.path, []).append(usage)
    return grouped


def preview_of(usage: Usage, file_lines: List[str], context: int = 2) -> UsagePreview:
    """
    :param file_lines: the lines of the file of the usage
    :param context: how many lines to show before and after the line of the usage
    """
    first = max(1, usage.line - context)
    lines = file_lines[first - 1 : usage.line + context]
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    indent = min(indents, default=0)
    return UsagePreview(
        first_line=first,
        lines=[line[indent:] for line in lines],
        index=usage.line - first,
        column=max(0, usage.column - indent),
        length=usage.length,
    )
