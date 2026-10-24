import hashlib
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

from openhasp_config_manager.gui.domain.gui_state import STATE_DIR_NAME

# folders that tools create next to the config files
# (and the folder with the state file of the GUI, which the GUI writes itself)
_IGNORED_FOLDERS = {".git", ".idea", ".vscode", ".venv", "__pycache__", "node_modules", STATE_DIR_NAME}
# temporary files of editors and tools (vim: `4913` to test write access, `.swp`; emacs: `.#name`, `#name#`)
_IGNORED_SUFFIXES = ("~", ".swp", ".swx", ".tmp", ".bak", ".orig", ".pyc")
_IGNORED_NAMES = {"4913", ".DS_Store"}


def is_relevant_change(path: Path, ignored_roots: Iterable[Path] = ()) -> bool:
    """
    Whether a change of a file or folder in the config directory can change what the editor shows.
    Temporary files of editors and LLM tools, version control and the generated output are not.
    """
    name = path.name
    if name in _IGNORED_NAMES or name.startswith((".#", "#")) or name.endswith(_IGNORED_SUFFIXES):
        return False
    if any(part in _IGNORED_FOLDERS for part in path.parts):
        return False
    return not any(path.is_relative_to(root) for root in ignored_roots)


def content_hash(path: Path) -> Optional[str]:
    """:return: the hash of the content of a file, None if it doesn't exist (or isn't a file)"""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, IsADirectoryError):
        return None


class OwnWrites:
    """
    Remembers what the app wrote itself (Save), so the change events of those writes don't count as changes made by
    someone else. A file counts as written by the app while it still has exactly the content the app wrote.
    """

    def __init__(self):
        self._hashes: Dict[Path, str] = {}

    def written(self, path: Path, content: str):
        self._hashes[path] = hashlib.sha256(content.encode()).hexdigest()

    def foreign(self, paths: Iterable[Path]) -> Set[Path]:
        """:return: the paths that don't have the content the app wrote last (or never wrote)"""
        return {path for path in paths if self._hashes.get(path) is None or self._hashes[path] != content_hash(path)}
