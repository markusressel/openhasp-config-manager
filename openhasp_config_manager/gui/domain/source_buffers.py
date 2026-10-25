"""
The text of the files the user edits in the text editor, and what happens to it when the file changes on disk. Qt-free.

A buffer remembers the text of the file as it was on disk (`disk_text`) when it was loaded or saved, to tell its own
changes (`text` differs) from those of someone else (the file differs from `disk_text`).
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional


class DiskChange(Enum):
    # the file has the text of the buffer (or the one it was loaded with)
    NONE = "none"
    # the buffer had no changes, it follows the file
    RELOADED = "reloaded"
    # the buffer has changes of its own and the file changed too: the user decides
    CONFLICT = "conflict"
    # the file was deleted, the buffer had no changes
    DELETED = "deleted"


def read_text(path: Path) -> Optional[str]:
    """:return: the text of a file, None if it doesn't exist"""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


@dataclass
class SourceBuffer:
    path: Path
    # the text of the file when the buffer was loaded or saved last (None: the file doesn't exist)
    disk_text: Optional[str]
    text: str
    # the file differs from `disk_text` and the buffer has changes: waiting for the decision of the user
    conflict: bool = False

    @classmethod
    def open(cls, path: Path) -> "SourceBuffer":
        text = read_text(path)
        return cls(path=path, disk_text=text, text=text or "")

    @property
    def is_dirty(self) -> bool:
        return self.text != (self.disk_text or "")

    def set_text(self, text: str):
        self.text = text

    def on_disk_changed(self) -> DiskChange:
        """Look at the file after a change event, and follow it if the buffer has no changes of its own."""
        current = read_text(self.path)
        if current == self.disk_text:
            return DiskChange.NONE
        if current is not None and current == self.text:
            # someone saved what the buffer has
            self.disk_text = current
            self.conflict = False
            return DiskChange.NONE
        if self.is_dirty:
            self.conflict = True
            return DiskChange.CONFLICT
        if current is None:
            return DiskChange.DELETED
        self.disk_text = current
        self.text = current
        return DiskChange.RELOADED

    def reload(self):
        """Take the text of the file, dropping the changes of the buffer."""
        text = read_text(self.path)
        self.disk_text = text
        self.text = text or ""
        self.conflict = False

    def keep_mine(self):
        """Keep the text of the buffer over the file: the file counts as known, the buffer stays changed until it is saved."""
        self.disk_text = read_text(self.path)
        self.conflict = False

    def save(self) -> str:
        """
        Write the text to the file (also if it changed on disk meanwhile: the caller asks the user first).
        :return: the text that was written
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.text, encoding="utf-8")
        self.disk_text = self.text
        self.conflict = False
        return self.text


class SourceBuffers:
    """The open buffers, in the order of the tabs."""

    def __init__(self, opener: Callable[[Path], SourceBuffer] = SourceBuffer.open):
        self._opener = opener
        self._buffers: Dict[Path, SourceBuffer] = {}

    def __iter__(self):
        return iter(self._buffers.values())

    def __len__(self):
        return len(self._buffers)

    def __contains__(self, path: Path) -> bool:
        return path.resolve() in self._buffers

    def get(self, path: Path) -> Optional[SourceBuffer]:
        return self._buffers.get(path.resolve())

    def open(self, path: Path) -> SourceBuffer:
        """:return: the buffer of a file, loaded if it is not open yet"""
        path = path.resolve()
        if path not in self._buffers:
            self._buffers[path] = self._opener(path)
        return self._buffers[path]

    def close(self, path: Path):
        self._buffers.pop(path.resolve(), None)

    def dirty(self) -> List[SourceBuffer]:
        return [buffer for buffer in self._buffers.values() if buffer.is_dirty]

    def on_disk_changed(self, paths: Iterable[Path]) -> Dict[Path, DiskChange]:
        """:return: what happened to every open buffer among the changed paths (the others are left out)"""
        result = {}
        for path in paths:
            buffer = self._buffers.get(path.resolve())
            if buffer is not None:
                result[buffer.path] = buffer.on_disk_changed()
        return result
