"""
References from one file to another (`run L:/pages.jsonl` in a .cmd file, the path of an `!include` in a .jsonl file), for
Ctrl+click in the text editor. Qt-free.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set

from openhasp_config_manager.gui.domain.source.syntax import Language

_REFERENCE = re.compile(r"L:/[^\s\"']+?\.(?:jsonl|cmd)(?=$|[\s\"'])")
# the path of an `!include` (without its quotes)
_INCLUDE = re.compile(r'"!include"\s*:\s*"([^"]+)"')


@dataclass(frozen=True)
class Link:
    start: int
    end: int
    # the file name on the plate, without `L:/` (a file link), the path of an `!include` (an include link), or the variable (a
    # variable link)
    target: str
    # "file" for a reference to a file, "include" for the path of an `!include` (relative to the config directory), "variable" for
    # a part of a variable in a template, "usages" for the key of a variable
    kind: str = "file"


def find_links(line: str, language: Language) -> list:
    """:return: the references to files in a line"""
    if language == Language.JSONL:
        return [Link(match.start(1), match.end(1), match.group(1), kind="include") for match in _INCLUDE.finditer(line)]
    if language != Language.CMD:
        return []
    return [Link(match.start(), match.end(), match.group()[len("L:/") :]) for match in _REFERENCE.finditer(line)]


def link_at(line: str, column: int, language: Language) -> Optional[Link]:
    return next((link for link in find_links(line, language) if link.start <= column < link.end), None)


def include_targets(config_dir: Path) -> List[str]:
    """:return: the .jsonl files of a config directory as an `!include` names them, sorted, without hidden folders and files"""
    return sorted(path.relative_to(config_dir).as_posix() for path in link_targets(config_dir) if path.suffix == ".jsonl")


def plate_names(path: Path, config_dir: Path) -> Set[str]:
    """
    :return: the names a file can have on the plate: its path below the folder that is its root (`common`, the folder of a
        device, ...) with `_` between the parts. Which folder that is depends on the config, so every tail of the path counts.
    """
    parts = path.relative_to(config_dir).parts
    return {"_".join(parts[index:]) for index in range(len(parts))}


def link_targets(config_dir: Path) -> List[Path]:
    """:return: the files of a config directory a reference can be to, without hidden folders and files"""
    return [
        file
        for suffix in ("*.jsonl", "*.cmd")
        for file in config_dir.rglob(suffix)
        if not any(part.startswith(".") for part in file.relative_to(config_dir).parts)
    ]


def resolve_link(target: str, files: Iterable[Path], config_dir: Path, near: Path) -> Optional[Path]:
    """:return: the file that is `target` on the plate. If several are, the one closest to the file with the reference (`near`)."""
    candidates = [path for path in files if target in plate_names(path, config_dir)]
    if not candidates:
        return None

    def closeness(path: Path) -> int:
        shared = 0
        for ours, theirs in zip(path.parts, near.parts):
            if ours != theirs:
                break
            shared += 1
        return shared

    return max(candidates, key=closeness)
