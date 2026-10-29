import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from openhasp_config_manager.gui.domain.connection import ConnectionStatus
from openhasp_config_manager.gui.domain.draft.model import ComponentSource
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.domain.problems import Problem, object_name
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.jsonl.includes import ObjectOrigin

LOGGER = logging.getLogger(__name__)

# the folder in the config directory the GUI shares its state in, for tools that work on the config files
STATE_DIR_NAME = ".openhasp-config-manager"
STATE_FILE_NAME = "gui-state.json"
README_FILE_NAME = "README.md"
SCHEMA_VERSION = 1

_MAX_ERROR_LENGTH = 500
# the properties of an object that say where it is drawn
_GEOMETRY_KEYS = ("x", "y", "w", "h")

README = """\
# GUI state

While the openhasp-config-manager GUI runs, it keeps `gui-state.json` in this folder up to date: what the user has open, the
warnings and errors it shows, and what it can't load. It is meant for tools (e.g. an LLM) that edit the config files next to the
GUI, as context. **Edit the config files, not this folder**: nothing here is read back, and the GUI reloads the files when they
change. This folder is ignored by git and rewritten by the GUI.

Read the file before and after you edit, and trust it only while it is current:

- `running` is `true` while the GUI runs. After a crash it stays `true`: check that the process `pid` exists, and that `updated` is
  recent (it changes whenever anything else does).
- Without the GUI, `openhasp-config-manager check -c <config dir> [--json]` reports the same problems for all devices and pages, and
  what a deployment would fail on (exit code 1 on errors). Run it after your edits too (`check_command` is that command).
- All paths are relative to the config directory (the parent of this folder). Lines start at 1.

## Format (`schema` 1)

- `check_command`: the command that checks this config directory without the GUI (all devices and pages).
- `devices`: names of the devices in the config directory.
- `device`: the device that is open, or `null`.
  - `name`, `folder`, `cmd` (the script whose pages are shown), `screen` (`width`, `height`).
  - `files`: the .jsonl files the plate loads, in the order it loads them, with the `pages` each has objects on and whether
    it is `shared` (in `common/`, used by other devices too). Later files are drawn on top.
  - `page`, `pages`: the page in the preview, and all pages that have objects.
  - `edit_mode`: whether the user edits objects. `live_preview`: whether the draft is sent to the plate while editing.
  - `selection`: the selected objects: `name` (`p<page>b<id>`), `id`, `page`, `type`, `file`, `line` (`null` if only in the draft),
    and where it is drawn: `rendered` and `source` (see `problems`), and `include` for an included object (see `problems`).
  - `new_objects_file`: the file new objects of the user go into.
  - `draft`: `modified` is `true` if the user has unsaved changes in the GUI. They are not in the files yet, and a file the user
    changed on disk meanwhile can't be saved over. `files` lists, per file, the `changed`, `added` and `deleted` objects.
- `editor`: the text editor of the GUI, where files are edited as text. `mode` (`source`, `split`, `rendered`: which of the text editor and the
  rendered JSONL are shown), `current` (the file of the tab that is shown, or `null`), and `files`, the open tabs:
  `file`, `dirty` (the text has changes that are not saved: the file on disk is the older version), `conflict` (the file changed on
  disk while it has unsaved changes, the user chooses which to keep), `line` and `column` of the cursor.
- `problems`: warnings and errors of the objects on the open page (same as the GUI shows): `severity`, `message`, `object`, `file`,
  `line`, `rendered` and `source`, `devices`. Only the open page is checked.
  - `rendered`: the `x`, `y`, `w`, `h` the object has after rendering (what the plate gets); only those it has.
  - `source`: the same properties as written in the file, with their templates, e.g. `"w": "33%"` or `"x": "{{ ... }}"`. Shows
    which are templates (don't replace one by a number just to fix a position that depends on the screen size).
  - `devices`: the devices that load the file. More than one if the file is shared: a change there affects all of them.
  - `include`: only for an object that an `!include` directive puts into the file. `file` and `line` of the object are then the
    ones of the directive, `source` is the object as written in the part. `include` has the `file` and `line` of the object in
    the part (the file to change), and `chain`: the directives that lead to it, outermost first, each with its `file`, `line`,
    `vars` and `loop` (the values of its `for` variables for this instance). The object is read-only in the GUI.
- `load_error`: why the device could not be loaded (e.g. invalid JSON in a file), or `null`. The GUI keeps showing the last good
  state until the files can be loaded again.
- `files_changed_on_disk`: files that changed while the draft has unsaved changes (the GUI asks the user what to do), else `[]`.
- `connection`: `state` (`no_device`, `connecting`, `broker_unreachable`, `plate_unknown`, `plate_online`, `plate_offline`), `error`,
  `sending`, `out_of_sync_pages` (pages that may show something else on the plate than in the GUI).
- `last_operation`: the last save, deploy or failure the GUI reported: `ok`, `message`, `time`.
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def relative(path: Path, config_dir: Path) -> str:
    try:
        return path.resolve().relative_to(config_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _short(text: Optional[str]) -> Optional[str]:
    if text is None or len(text) <= _MAX_ERROR_LENGTH:
        return text
    return text[:_MAX_ERROR_LENGTH] + "…"


def describe_object(session: PlateSession, obj: Dict[str, Any], config_dir: Path) -> Dict[str, Any]:
    """:return: where an object is: its name, type, file and line, and where it is drawn (rendered and as written)"""
    component = session.component_of(obj)
    source = session.source_of(obj)
    return {
        "name": object_name(obj),
        "id": obj.get("id"),
        "page": obj.get("page"),
        "type": obj.get("obj"),
        "file": relative(component.path, config_dir),
        "line": session.line_of(obj),
        "rendered": {key: obj[key] for key in _GEOMETRY_KEYS if key in obj},
        "source": {key: source[key] for key in _GEOMETRY_KEYS if key in source},
        **_describe_origin(session.origin_of(obj), config_dir),
    }


def _describe_origin(origin: Optional[ObjectOrigin], config_dir: Path) -> Dict[str, Any]:
    """:return: `include` with where an included object is written, nothing for the other objects"""
    if origin is None:
        return {}
    chain = [
        {"file": relative(step.file, config_dir), "line": step.line, "vars": _json(step.vars), "loop": _json(step.loop)}
        for step in origin.includes
    ]
    return {"include": {"file": relative(origin.file, config_dir), "line": origin.line, "chain": chain}}


def _json(value: Any) -> Any:
    """:return: the value with what JSON can't hold as text (the values of templates can be anything)"""
    return json.loads(json.dumps(value, default=str))


def describe_problems(
    session: PlateSession, problems: List[Problem], config_dir: Path, devices: Sequence[Device] = ()
) -> List[Dict[str, Any]]:
    """:param devices: all devices of the config directory, to tell which of them load the file of a problem"""
    result = []
    for problem in problems:
        location = describe_object(session, problem.obj, config_dir)
        path = session.component_of(problem.obj).path
        result.append(
            {
                "severity": problem.severity.value,
                "message": problem.message,
                "object": location["name"],
                "file": location["file"],
                "line": location["line"],
                "rendered": location["rendered"],
                "source": location["source"],
                **({"include": location["include"]} if "include" in location else {}),
                "devices": sorted(device.name for device in devices if any(c.path == path for c in device.jsonl)),
            }
        )
    return result


def describe_draft(session: PlateSession, config_dir: Path) -> Dict[str, Any]:
    """:return: whether the draft has unsaved changes, and which objects of which files they are about"""
    files = []
    for changes in session.changes():
        sources = changes.component.sources
        files.append(
            {
                "file": relative(changes.component.path, config_dir),
                "changed": [object_name(sources[index]) for index in sorted(changes.changes)],
                "added": [object_name(source) for source in changes.additions],
                "deleted": [object_name(sources[index]) for index in sorted(changes.deletions)],
            }
        )
    return {"modified": session.is_dirty, "files": files}


def describe_files(components: List[ComponentSource], working_objects: Dict[str, List[Dict]], config_dir: Path):
    return [
        {
            "file": relative(component.path, config_dir),
            "shared": component.is_common,
            "pages": sorted({obj["page"] for obj in working_objects.get(component.key, []) if obj.get("page") is not None}),
        }
        for component in components
    ]


@dataclass(frozen=True)
class EditorTab:
    path: Path
    dirty: bool
    # the file changed on disk while the tab has changes
    conflict: bool
    # the cursor, both starting at 1
    line: int
    column: int


def describe_editor(mode: str, tabs: List[EditorTab], current: Optional[Path], config_dir: Path) -> Dict[str, Any]:
    """:return: what the text editor shows: which files are open, which have unsaved text, and where the cursor is"""
    return {
        "mode": mode,
        "current": None if current is None else relative(current, config_dir),
        "files": [
            {
                "file": relative(tab.path, config_dir),
                "dirty": tab.dirty,
                "conflict": tab.conflict,
                "line": tab.line,
                "column": tab.column,
            }
            for tab in tabs
        ],
    }


def describe_connection(status: ConnectionStatus) -> Dict[str, Any]:
    return {
        "state": status.link.value,
        "error": _short(status.error),
        "sending": status.sending,
        "out_of_sync_pages": sorted(status.out_of_sync_pages),
    }


class GuiStateFile:
    """
    The state file of the GUI in the config directory (see README). Writing it never fails the app: a config directory
    that is read-only just has no state file.
    """

    def __init__(self, config_dir: Path):
        self.folder = config_dir / STATE_DIR_NAME
        self.path = self.folder / STATE_FILE_NAME
        self._last_content: Optional[str] = None
        self._failed = False

    def write(self, state: Dict[str, Any]):
        """Replace the file atomically, so a reader never sees half of it. Nothing is written if only `updated` differs."""
        compared = json.dumps({**state, "updated": None}, indent=2, ensure_ascii=False)
        if compared == self._last_content and self.path.exists():
            return
        try:
            self._ensure_folder()
            content = json.dumps(state, indent=2, ensure_ascii=False) + "\n"
            with tempfile.NamedTemporaryFile("w", dir=self.folder, prefix=".gui-state-", suffix=".tmp", delete=False) as tmp:
                tmp.write(content)
            os.replace(tmp.name, self.path)
        except OSError as ex:
            if not self._failed:
                LOGGER.warning(f"Can't write the GUI state to {self.path}: {ex}")
            self._failed = True
            return
        self._failed = False
        self._last_content = compared

    def _ensure_folder(self):
        self.folder.mkdir(exist_ok=True)
        # the folder ignores itself, no matter how the user's repository is set up
        gitignore = self.folder / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n")
        readme = self.folder / README_FILE_NAME
        if not readme.exists() or readme.read_text() != README:
            readme.write_text(README)
