"""
Layout dumps (README §6.1): the rendered owned objects of every page, as a JSONL file in the openhasp-configs format, so
a code-defined page can be previewed in the Qt editor, diffed between instances, or frozen into a JSONL file on flash.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import orjson


def dump_lines(objects: List[Dict[str, Any]], declarations: Dict[int, Optional[str]]) -> str:
    """
    The JSONL of a page: one line per object, each preceded by a `//` comment with its declaration site (comments are
    removed by openhasp-config-manager's preprocessor).
    """
    lines = []
    for obj in objects:
        declaration = declarations.get(obj["id"])
        if declaration:
            lines.append(f"// {declaration}")
        lines.append(orjson.dumps(obj).decode("utf-8"))
    return "\n".join(lines) + "\n"


def write_dump(
    directory: Path, plate: str, page: int, objects: List[Dict[str, Any]], declarations: Dict[int, Optional[str]]
) -> Path:
    """Writes `<directory>/<plate>/p<page>.jsonl` and returns its path."""
    path = directory / plate / f"p{page}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_lines(objects, declarations), encoding="utf-8")
    return path
