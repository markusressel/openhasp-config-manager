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
from openhasp_config_manager.gui.domain.draft.page_objects import get_navigable_page_indices
from openhasp_config_manager.gui.domain.draft.part_focus import PartFocus
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.domain.problems import Problem, object_name
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.jsonl.includes import ObjectOrigin

LOGGER = logging.getLogger(__name__)

# the folder in the config directory the GUI shares its state in, for tools that work on the config files
STATE_DIR_NAME = ".openhasp-config-manager"
STATE_FILE_NAME = "gui-state.json"
# the plate as the preview of the active tab shows it (see README)
PREVIEW_FILE_NAME = "preview.png"
# the plate of each open device as its tab shows it: `preview/<device>/current.png`, next to the images of the pages from the
# files on disk that the `preview` command writes there (`page_<n>.png`)
DEVICE_PREVIEW_DIR_NAME = "preview"
DEVICE_PREVIEW_FILE_NAME = "current.png"
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
- To see the pages, look at the images: `preview.png` is the page the active tab of the GUI shows (see `device.preview`),
  `preview/<device>/current.png` the page of each open device (see `tabs`), `preview_command` renders any page from the files
  on disk.
- All paths are relative to the config directory (the parent of this folder). Lines start at 1.

## Format (`schema` 1)

- `check_command`: the command that checks this config directory without the GUI (all devices and pages).
- `preview_command`: the command that renders all pages of all devices from the files on disk, without the GUI, into
  `.openhasp-config-manager/preview/<device>/page_<n>.png` (it prints the path of each image). Add `-d <device>` and `-p <page>`
  for fewer, `--scale 2` for larger images.
- `devices`: names of the devices in the config directory.
- `tabs`: the tabs of the GUI, in their order. A tab shows the pages of a device, or one part of a device (a part tab, "Edit
  the part"). Several devices can be open at once, each with its own connection to its plate; the other keys of this file
  (`device`, `problems`, `connection`) are about the active tab only.
  - `kind`: `device` or `part`. `device`: the name of the device.
  - `part`: the part of a part tab (the file), else `null`. `instance`: the `!include` whose objects the part tab shows and
    changes (as in `part_mode`), else `null`. `alone`: `true` if the part tab shows the part on its own (see `part_mode`).
  - `page`: the page the tab shows, `null` while the device loads.
  - `connection`: the state of the connection to the plate of the device (as `connection.state`). `live_preview`: whether
    the draft is sent to the plate of the device while editing, also from other tabs.
  - `unsaved`: whether the files the tab shows have unsaved changes (of a part tab: the part and the files that include the
    instance).
  - `preview`: the image of the plate of the device as the GUI shows it, or `null` while the device loads: `file`
    (`.openhasp-config-manager/preview/<device>/current.png`) and `updated`, as `device.preview`. It shows the page of the tab of
    the device that was active last (a device has one image, also with several tabs), with its unsaved changes. The image is
    removed when the last tab of the device closes.
- `active_tab`: the index of the active tab in `tabs`, `null` without tabs.
- `device`: the device of the active tab, or `null`.
  - `name`, `folder`, `cmd` (the script whose pages are shown), `screen` (`width`, `height`).
  - `files`: the .jsonl files the plate loads, in the order it loads them, with the `pages` each has objects on and whether
    it is `shared` (in `common/`, used by other devices too). Later files are drawn on top.
  - `page`, `pages`: the page in the preview, and all pages that have objects.
  - `edit_mode`: whether the user edits objects. `live_preview`: whether the draft is sent to the plate while editing.
  - `selection`: the selected objects: `name` (`p<page>b<id>`), `id`, `page`, `type`, `file`, `line` (`null` if only in the draft),
    and where it is drawn: `rendered` and `source` (see `problems`), and `include` for an included object (see `problems`).
  - `new_objects_file`: the file new objects of the user go into.
  - `part_mode`: `null`, or the part the user edits in the active tab, a part tab: `part` (the file), `instance` (the
    `!include` whose objects are shown and changed, `null` once they are all removed) and `shared` (in `common/`). A change to
    the objects of the instance changes the part, so every instance (and every device that includes a shared part) follows.
    `alone` is `true` if no page of the device includes the part: the tab then shows the part on its own (with `vars` the
    user enters, which are not saved), `files` is empty, and the `file` of an object is the
    `!include` that shows the part (`<part> (alone).jsonl`, a file that doesn't exist).
  - `draft`: `modified` is `true` if the user has unsaved changes in the GUI. They are not in the files yet, and a file the user
    changed on disk meanwhile can't be saved over. `files` lists, per file, the `changed`, `added` and `deleted` objects.
  - `loaded`: when the GUI read the files of the device from disk the last time (with milliseconds). It reloads them after
    they changed (unless the draft has changes, see `files_changed_on_disk`): after you edited a file, wait until `loaded` is
    later than your change (or `load_error` says why it can't load) before you trust the rest of `device`, `problems` and the
    preview.
  - `preview`: the image of the plate as the active tab shows it, or `null`: `file` (a PNG in the native resolution of the
    plate, `.openhasp-config-manager/preview.png`, the same image as the `preview` of the tab) and `updated` (when the image changed the last time). It shows the open `page`
    with the unsaved changes, the selected objects with a frame and, in part mode, only the objects of the instance (the
    other objects dimmed if the user turned on "Show the page"). It is written
    before the state, so it is the image of the state you read. Other pages and devices, from the files on disk:
    `openhasp-config-manager preview -c <config dir> [-d <device>] [-p <page>]` (see `preview_command`).
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
    `vars` and `loop` (the values of its `for` variables for this instance). The object is read-only in the GUI, except in
    part mode (see `part_mode`).
- `load_error`: why the device could not be loaded (e.g. invalid JSON in a file), or `null`. The GUI keeps showing the last good
  state until the files can be loaded again.
- `files_changed_on_disk`: files that changed while the draft has unsaved changes (the GUI asks the user what to do), else `[]`.
- `connection`: the connection to the plate of the device of the active tab: `state` (`no_device`, `connecting`, `broker_unreachable`, `plate_unknown`, `plate_online`, `plate_offline`), `error`,
  `sending`, `out_of_sync_pages` (pages that may show something else on the plate than in the GUI).
- `last_operation`: the last save, deploy or failure the GUI reported: `ok`, `message`, `time`.
"""


def ensure_state_folder(config_dir: Path) -> Path:
    """:return: the state folder of the config directory (see README), created if it doesn't exist"""
    folder = config_dir / STATE_DIR_NAME
    folder.mkdir(exist_ok=True)
    # the folder ignores itself, no matter how the user's repository is set up
    gitignore = folder / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")
    readme = folder / README_FILE_NAME
    if not readme.exists() or readme.read_text() != README:
        readme.write_text(README)
    return folder


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


def describe_part_mode(focus: Optional[PartFocus], config_dir: Path) -> Optional[Dict[str, Any]]:
    """
    :param focus: the part mode of the preview, None outside of part mode
    :return: the part that is edited in part mode, and the instance that is shown, or None
    """
    if focus is None or not focus.is_active:
        return None
    session = focus.session
    return {
        "part": relative(focus.part, config_dir),
        # an instance whose objects were all removed is not in the draft anymore
        "instance": focus.describe(),
        "shared": session.part_source(focus.part).is_common,
        "alone": session.is_part_alone,
    }


def describe_draft(session: PlateSession, config_dir: Path) -> Dict[str, Any]:
    """:return: whether the draft has unsaved changes, and which objects of which files they are about"""
    files = []
    for changes in session.changes():
        sources = changes.component.sources
        files.append(
            {
                "file": relative(changes.component.path, config_dir),
                "changed": [object_name(sources[index]) for index in sorted(set(changes.changes) | set(changes.removals))],
                "added": [object_name(source) for source in changes.additions],
                "deleted": [object_name(sources[index]) for index in sorted(changes.deletions)],
            }
        )
    return {"modified": session.is_dirty, "files": files}


def describe_device(
    session: PlateSession,
    device: Device,
    cmd: str,
    page: int,
    edit_mode: bool,
    live_preview: bool,
    selection: List[Dict[str, Any]],
    target_component: Optional[str],
    config_dir: Path,
    part_focus: Optional[PartFocus] = None,
) -> Dict[str, Any]:
    """
    :param cmd: the startup script the device is loaded with
    :param page: the page in the preview
    :param selection: the selected objects
    :param target_component: the key of the file new objects go into (in part mode: the path of the part), None without one
    :param part_focus: the part mode of the preview, None outside of part mode
    :return: the `device` part of the state (see README), without `preview`
    """
    screen = device.config.openhasp_config_manager.device.screen
    return {
        "name": device.name,
        "folder": relative(device.path, config_dir),
        "cmd": cmd,
        "screen": {"width": screen.width, "height": screen.height},
        "files": describe_files(session.components, session.working_objects, config_dir),
        "page": page,
        "pages": get_navigable_page_indices(session.working_objects),
        "edit_mode": edit_mode,
        "live_preview": live_preview,
        "selection": [describe_object(session, obj, config_dir) for obj in selection],
        "new_objects_file": None
        if target_component is None
        else relative(
            Path(target_component)
            if part_focus is not None and part_focus.is_active
            else next(c.path for c in session.components if c.key == target_component),
            config_dir,
        ),
        "part_mode": describe_part_mode(part_focus, config_dir),
        "draft": describe_draft(session, config_dir),
        "loaded": session.loaded_at.isoformat(timespec="milliseconds"),
    }


def describe_files(components: List[ComponentSource], working_objects: Dict[str, List[Dict]], config_dir: Path):
    return [
        {
            "file": relative(component.path, config_dir),
            "shared": component.is_common,
            "pages": sorted({obj["page"] for obj in working_objects.get(component.key, []) if obj.get("page") is not None}),
        }
        for component in components
        # what shows a part on its own is in no file
        if not component.is_scratch
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


@dataclass(frozen=True)
class PreviewTab:
    """A tab of the preview (see `MainWindow.device_tabs`), as the state file describes it."""

    device: str
    # the part of a part tab, None for a tab of the pages of the device
    part: Optional[Path]
    # where the instance of a part tab is included (see `PartFocus.describe`), None if it has no objects or in a device tab
    instance: Optional[str]
    # a part tab that shows the part on its own
    alone: bool
    # None while the device loads
    page: Optional[int]
    connection: ConnectionStatus
    live_preview: bool
    unsaved: bool


def describe_tabs(tabs: List[PreviewTab], active: Optional[int], config_dir: Path) -> Dict[str, Any]:
    """
    :param active: the index of the active tab, None without tabs
    :return: the `tabs` (without their `preview`) and `active_tab` of the state (see README)
    """
    return {
        "tabs": [
            {
                "kind": "device" if tab.part is None else "part",
                "device": tab.device,
                "part": None if tab.part is None else relative(tab.part, config_dir),
                "instance": tab.instance,
                "alone": tab.alone,
                "page": tab.page,
                "connection": tab.connection.link.value,
                "live_preview": tab.live_preview,
                "unsaved": tab.unsaved,
            }
            for tab in tabs
        ],
        "active_tab": active,
    }


def describe_connection(status: ConnectionStatus) -> Dict[str, Any]:
    return {
        "state": status.link.value,
        "error": _short(status.error),
        "sending": status.sending,
        "out_of_sync_pages": sorted(status.out_of_sync_pages),
    }


class _Image:
    """An image in the state folder, replaced atomically when it changed."""

    def __init__(self, path: Path):
        self.path = path
        self._last: Optional[bytes] = None
        self._updated: Optional[str] = None

    def write(self, png: bytes, config_dir: Path) -> Dict[str, Any]:
        """
        :return: what the state says about the image (see `device.preview` in README)
        :raises OSError: if it can't be written
        """
        if png != self._last or not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "wb", dir=self.path.parent, prefix=".preview-", suffix=".tmp", delete=False
            ) as tmp:
                tmp.write(png)
            os.replace(tmp.name, self.path)
            self._last = png
            self._updated = now()
        return self.reference(config_dir)

    @property
    def written(self) -> bool:
        """Whether the image was written and is still there."""
        return self._last is not None and self.path.exists()

    def reference(self, config_dir: Path) -> Dict[str, Any]:
        return {"file": relative(self.path, config_dir), "updated": self._updated}

    def remove(self):
        self._last = None
        try:
            self.path.unlink(missing_ok=True)
        except OSError as ex:
            LOGGER.warning(f"Can't remove the preview {self.path}: {ex}")


class GuiStateFile:
    """
    The state file of the GUI in the config directory (see README). Writing it never fails the app: a config directory
    that is read-only just has no state file.
    """

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir.resolve()
        self.folder = self.config_dir / STATE_DIR_NAME
        self.path = self.folder / STATE_FILE_NAME
        self.preview_path = self.folder / PREVIEW_FILE_NAME
        self._last_content: Optional[str] = None
        self._preview = _Image(self.preview_path)
        # the images of the open devices (see `write_device_preview`), by device
        self._device_previews: Dict[str, _Image] = {}
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

    def write_preview(self, png: Optional[bytes]) -> Optional[Dict[str, Any]]:
        """
        Replace the image of the preview of the active tab (`preview.png`) atomically, if it changed.
        :param png: the image, None if no page is shown (the image is removed)
        :return: what the state says about the image (`device.preview`, see README), None without one
        """
        return self._write_image(self._preview, png)

    def device_preview_path(self, device: str) -> Path:
        return self.folder / DEVICE_PREVIEW_DIR_NAME / device / DEVICE_PREVIEW_FILE_NAME

    def has_device_preview(self, device: str) -> bool:
        """Whether the image of a device was written (see `write_device_preview`) and is still there."""
        image = self._device_previews.get(device)
        return image is not None and image.written

    def write_device_preview(self, device: str, png: Optional[bytes]) -> Optional[Dict[str, Any]]:
        """
        Replace the image of an open device (`preview/<device>/current.png`) atomically, if it changed.
        :param png: the image, None if the device shows no page (the image is removed)
        :return: what the state says about the image (`tabs[].preview`, see README), None without one
        """
        image = self._device_previews.setdefault(device, _Image(self.device_preview_path(device)))
        return self._write_image(image, png)

    def device_preview(self, device: str) -> Optional[Dict[str, Any]]:
        """:return: what the state says about the image of a device that was written last, None without one"""
        if not self.has_device_preview(device):
            return None
        return self._device_previews[device].reference(self.config_dir)

    def remove_device_previews(self, keep: Sequence[str] = ()):
        """
        Remove the images of the devices that are not open anymore (their last tab closed), and those left by an earlier run
        (on start, with nothing to `keep`). The images of the `preview` command next to them stay.
        """
        folder = self.folder / DEVICE_PREVIEW_DIR_NAME
        paths = {self.device_preview_path(device) for device in self._device_previews}
        if folder.is_dir():
            paths |= set(folder.glob(f"*/{DEVICE_PREVIEW_FILE_NAME}"))
        kept = {self.device_preview_path(device) for device in keep}
        for path in paths - kept:
            image = self._device_previews.pop(path.parent.name, None) or _Image(path)
            if path.exists():
                image.remove()
            try:
                # the folder of a device the `preview` command didn't write images into
                path.parent.rmdir()
            except OSError:
                pass

    def _write_image(self, image: _Image, png: Optional[bytes]) -> Optional[Dict[str, Any]]:
        if png is None:
            image.remove()
            return None
        try:
            self._ensure_folder()
            return image.write(png, self.config_dir)
        except OSError as ex:
            if not self._failed:
                LOGGER.warning(f"Can't write the preview to {image.path}: {ex}")
            self._failed = True
            return None

    def _ensure_folder(self):
        ensure_state_folder(self.config_dir)
