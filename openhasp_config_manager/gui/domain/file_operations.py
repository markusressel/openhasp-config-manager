"""
The file operations of the Files tree: new files and folders, rename, move and delete. Qt-free: a `FilePlan` says what an
operation changes, the GUI shows it, asks, and carries it out (`apply_plan`).

The plate knows a file by a flat name made of its path: `common/page/md/content.jsonl` is `L:/common_page_md_content.jsonl`,
`devices/<device>/pages/home.jsonl` is `L:/pages_home.jsonl` (see `ConfigManager._create_text_component_from_path`). Renaming or
moving a file changes that name, so the references to it change with it: `L:/<name>` in the .cmd and .jsonl files of the
devices that see the file, and the paths of the `!include`s that include it. An operation that would leave a reference of a
.cmd file without its file is refused: a device with such a reference can't be loaded at all.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from openhasp_config_manager.const import COMMON_FOLDER_NAME, DEVICES_FOLDER_NAME, SYSTEM_SCRIPTS
from openhasp_config_manager.manager import CONFIG_FILE_NAME

# the longest name of a file on the plate, see `DeviceValidator`
PLATE_NAME_MAX = 30

# the files the plate gets: their names on the plate come from their paths
_PLATE_SUFFIXES = {".jsonl", ".cmd", ".png", ".bin", ".ttf"}
# the text files that refer to other files
_TEXT_SUFFIXES = {".jsonl", ".cmd"}
_VARIABLE_SUFFIXES = {".yaml", ".yml"}
# the kinds of files that can be made: the content they start with
NEW_FILE_SUFFIXES = (".jsonl", ".cmd", ".yaml")
# a name on the plate can't have spaces or quotes (`run L:/a b.jsonl`), and folders become part of the names
_VALID_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*")
# `L:/<name>` of a .jsonl or .cmd file in a command (like `ConfigManager._find_jsonl_references_in_cmd_component`)
_RUN_REFERENCE = re.compile(r"""L:/([^\s"']+?\.(?:jsonl|cmd))(?![\w.\-])""")


@dataclass(frozen=True)
class FileReference:
    """A line of a file that is in the way of an operation, e.g. a `run L:/...` of a file that would be gone."""

    file: Path
    # starting at 1
    line: int
    # the text of the line, stripped
    text: str
    # where it is, for people: `devices/a/boot.cmd:3`
    location: str = ""


class FileOperationError(Exception):
    """
    An operation is not possible. `summary` says what would go wrong; with `references` (the lines to change first, which
    the GUI opens), `explanation` introduces them and `advice` says what to do.
    """

    def __init__(self, summary: str, references: Iterable[FileReference] = (), explanation: str = "", advice: str = ""):
        self.summary = summary
        self.references = list(references)
        self.explanation = explanation
        self.advice = advice
        super().__init__("\n\n".join(part for part in [summary, self.details] if part))

    @property
    def details(self) -> str:
        """:return: the explanation, the lines (`devices/a/boot.cmd:3   run L:/page.jsonl`) and the advice, as plain text"""
        lines = "\n".join(f"{reference.location}   {reference.text}" for reference in self.references)
        return "\n\n".join(part for part in [self.explanation, lines, self.advice] if part)


@dataclass
class FilePlan:
    """What an operation changes in the config directory. Carried out in this order: edits, new files, moves, deletions."""

    # e.g. "Rename common/a.jsonl to b.jsonl"
    description: str
    # the new content of files (at their paths before the moves)
    edits: Dict[Path, str] = field(default_factory=dict)
    # new files with their content, and new folders (content None)
    creates: List[Tuple[Path, Optional[str]]] = field(default_factory=list)
    # (from, to): a file or a whole folder
    moves: List[Tuple[Path, Path]] = field(default_factory=list)
    # files and folders that go to the trash
    deletes: List[Path] = field(default_factory=list)
    # what else the user should know, e.g. which references are changed
    notes: List[str] = field(default_factory=list)

    @property
    def touched(self) -> Set[Path]:
        """:return: the files and folders whose content or place changes"""
        return set(self.edits) | {path for path, _ in self.creates} | {path for move in self.moves for path in move} | set(
            self.deletes
        )


class ConfigFiles:
    """The files of a config directory, as the plates see them."""

    def __init__(self, cfg_root: Path):
        self.root = cfg_root.resolve()
        self.common = self.root / COMMON_FOLDER_NAME
        self.devices = self.root / DEVICES_FOLDER_NAME

    def device_dirs(self) -> List[Path]:
        return sorted(path for path in self.devices.iterdir() if path.is_dir()) if self.devices.is_dir() else []

    def device_of(self, path: Path) -> Optional[Path]:
        """:return: the device folder a path is in (or is), None for the common folder and the root"""
        path = path.resolve()
        if path.is_relative_to(self.devices) and path != self.devices:
            return self.devices / path.relative_to(self.devices).parts[0]
        return None

    def area_of(self, path: Path) -> Optional[Path]:
        """:return: the common folder or the device folder a path is in, None for the root and anything else"""
        path = path.resolve()
        if path.is_relative_to(self.common):
            return self.common
        return self.device_of(path)

    def plate_name(self, path: Path) -> Optional[str]:
        """:return: the name of a file on the plate (`common_page_md_content.jsonl`), None if the plate never gets it"""
        if path.suffix not in _PLATE_SUFFIXES:
            return None
        path = path.resolve()
        area = self.area_of(path)
        if area is None:
            return None
        parts = list(path.relative_to(area).parts)
        return "_".join([COMMON_FOLDER_NAME, *parts] if area == self.common else parts)

    def config_path(self, path: Path) -> str:
        """:return: the path relative to the config directory, as `!include`s write it"""
        return path.resolve().relative_to(self.root).as_posix()

    def is_protected(self, path: Path) -> Optional[str]:
        """:return: why a file or folder can't be renamed, moved or deleted, None if it can"""
        path = path.resolve()
        if path in (self.root, self.common, self.devices):
            return f"{path.name} is a folder the config directory needs."
        device = self.device_of(path)
        if device == path:
            return "The folder of a device is the device: its name is the name of the plate."
        if device is not None and path == device / CONFIG_FILE_NAME:
            return f"{CONFIG_FILE_NAME} holds the settings of the plate."
        if device is not None and path.parent == device and path.name in SYSTEM_SCRIPTS:
            return f"The plate runs {path.name} by its name."
        return None

    def deletion_blocked(self, path: Path) -> Optional[str]:
        """:return: why a file or folder can't be deleted, None if it can (see `plan_delete` for what else is checked)"""
        reason = self.is_protected(path)
        path = path.resolve()
        # the other startup scripts are optional: the plate runs them if they are there
        if reason is not None and path.parent == self.device_of(path) and path.suffix == ".cmd" and path.name != "boot.cmd":
            return None
        return reason

    def files_seeing(self, path: Path) -> List[Path]:
        """:return: the .cmd and .jsonl files that can refer to a file by its plate name (of all devices for the common folder)"""
        device = self.device_of(path)
        folders = [device] if device is not None else [self.common, *self.device_dirs()]
        return [file for folder in folders for file in _files(folder, _TEXT_SUFFIXES)]

    def jsonl_files(self) -> List[Path]:
        return [file for folder in [self.common, *self.device_dirs()] for file in _files(folder, {".jsonl"})]

    def names_of_device(self, device: Path, files: Optional[Iterable[Path]] = None) -> Set[str]:
        """:return: the plate names a device has: of its own files and of the common folder"""
        if files is None:
            files = [*_files(self.common, _PLATE_SUFFIXES), *_files(device, _PLATE_SUFFIXES)]
        return {name for name in (self.plate_name(file) for file in files) if name is not None}


def _files(folder: Path, suffixes: Set[str]) -> List[Path]:
    if not folder.is_dir():
        return []
    return sorted(file.resolve() for file in folder.rglob("*") if file.is_file() and file.suffix in suffixes)


def check_name(name: str, suffix: Optional[str] = None) -> Optional[str]:
    """
    :param suffix: the suffix a file name must have, None for a folder
    :return: what is wrong with a new name, None if nothing
    """
    if not name:
        return "Enter a name."
    if not _VALID_NAME.fullmatch(name):
        return "Use letters, digits, _, - and . only: the name becomes part of the file names on the plate."
    if suffix is not None and Path(name).suffix != suffix:
        return f"The name must end with {suffix}."
    return None


# --- the operations ---


def plan_create(files: ConfigFiles, folder: Path, name: str, run_from: Optional[Path] = None) -> FilePlan:
    """
    A new, empty file (.jsonl, .cmd or .yaml, by the suffix of its name) or, without a suffix, a new folder.
    :param run_from: a .cmd file that runs a new .jsonl file (`run L:/<name>` is added to it)
    :raises FileOperationError:
    """
    folder = folder.resolve()
    suffix = Path(name).suffix
    is_folder = suffix == ""
    if not is_folder and suffix not in NEW_FILE_SUFFIXES:
        raise FileOperationError(f"A new file is a {', '.join(NEW_FILE_SUFFIXES)} file.")
    error = check_name(name, None if is_folder else suffix)
    if error is not None:
        raise FileOperationError(error)
    if files.area_of(folder) is None and not (folder == files.root and suffix == ".yaml"):
        raise FileOperationError("Only variable files (.yaml) can be in the root of the config directory.")
    path = folder / name
    if path.exists():
        raise FileOperationError(f"{name} already exists.")
    kind = "folder" if is_folder else "file"
    plan = FilePlan(f"New {kind} {files.config_path(folder / name) if folder != files.root else name}")
    plan.creates.append((path, None if is_folder else ""))
    plate_name = files.plate_name(path)
    if plate_name is not None:
        _check_collisions(files, {path: plate_name}, set())
    if run_from is not None and plate_name is not None:
        content = run_from.read_text()
        plan.edits[run_from.resolve()] = content + ("" if content.endswith("\n") or not content else "\n") + (
            f"run L:/{plate_name}\n"
        )
        plan.notes.append(f"{run_from.name} runs it: run L:/{plate_name}")
    elif suffix == ".jsonl":
        plan.notes.append(f"No startup script runs it yet: add run L:/{plate_name} to a .cmd file.")
    if plate_name is not None:
        _check_lengths(files, plan, {path: plate_name}, note=True)
    return plan


def plan_move(files: ConfigFiles, path: Path, target: Path) -> FilePlan:
    """
    Rename or move a file or a folder: `target` is its new path (in the same folder for a rename). The references to the
    files are changed with them.
    :raises FileOperationError:
    """
    path, target = path.resolve(), target.resolve()
    reason = files.is_protected(path)
    if reason is not None:
        raise FileOperationError(f"{path.name} can't be renamed or moved. {reason}")
    if target.exists():
        raise FileOperationError(f"{files.config_path(target)} already exists.")
    if path.is_dir() and target.is_relative_to(path):
        raise FileOperationError("A folder can't be moved into itself.")
    error = check_name(target.name, path.suffix if path.is_file() else None)
    if error is not None:
        raise FileOperationError(error)
    if files.area_of(target.parent) is None and not (target.parent == files.root and path.suffix in _VARIABLE_SUFFIXES):
        raise FileOperationError("Only variable files (.yaml) can be in the root of the config directory.")
    if files.device_of(path) is not None and files.device_of(target) not in (None, files.device_of(path)):
        raise FileOperationError("Files can't be moved to another device.")

    verb = "Rename" if path.parent == target.parent else "Move"
    plan = FilePlan(f"{verb} {_shown(files, path)} to {target.name if verb == 'Rename' else _shown(files, target)}")
    plan.moves.append((path, target))
    moved = _moved_files(path, target)

    renames = {
        old: (files.plate_name(old), files.plate_name(new)) for old, new in moved.items() if files.plate_name(old) is not None
    }
    renames = {old: names for old, names in renames.items() if names[0] != names[1]}
    fonts = [old for old in renames if old.suffix == ".ttf"]
    if fonts:
        raise FileOperationError(
            f"The pages refer to fonts by their name, which would change: {', '.join(old.name for old in fonts)}. "
            "Move the fonts by hand."
        )
    if renames:
        _check_collisions(files, {moved[old]: new for old, (_, new) in renames.items()}, set(renames))
        _check_pages_config(files, renames)
        _add_reference_edits(files, plan, {old: names for old, names in renames.items()}, moved)
        _check_lengths(files, plan, {moved[old]: new for old, (_, new) in renames.items()})
    _add_include_edits(files, plan, moved)
    _check_run_references(files, plan, moved, deleted=set())

    variables = [old for old in moved if old.suffix in _VARIABLE_SUFFIXES]
    if variables and path.parent != target.parent:
        plan.notes.append(
            f"Its variables then apply to the files of {_shown(files, target.parent)} and its subfolders."
            if path.is_file()
            else "The variable files in it then apply to the files of the new folder."
        )
    if files.area_of(path) != files.area_of(target):
        plan.notes.append(
            "It is then shared with every device."
            if files.area_of(target) == files.common
            else "It is then only for this device: other devices don't see it anymore."
        )
    return plan


def plan_delete(files: ConfigFiles, path: Path) -> FilePlan:
    """
    Move a file or a folder to the trash. Refused while a .cmd file runs it or an `!include` includes it.
    :raises FileOperationError:
    """
    path = path.resolve()
    reason = files.deletion_blocked(path)
    if reason is not None:
        raise FileOperationError(f"{path.name} can't be deleted. {reason}")
    plan = FilePlan(f"Delete {_shown(files, path)}")
    plan.deletes.append(path)
    deleted = set(_moved_files(path, path))
    includes = _include_references(files, deleted)
    if includes:
        raise FileOperationError(
            "Other files still include it.",
            includes,
            explanation="It is included here:",
            advice="Remove the !include first." if len(includes) == 1 else "Remove these !includes first.",
        )
    _check_run_references(files, plan, {}, deleted)
    images = _image_references(files, deleted)
    if images:
        plan.notes.append(f"Still referenced as an image by: {', '.join(files.config_path(file) for file in sorted(images))}.")
    return plan


def apply_plan(plan: FilePlan, trash: Callable[[Path], None]):
    """
    Carry out a plan.
    :param trash: moves a file or folder to the trash
    :raises OSError:
    """
    for path, content in plan.edits.items():
        path.write_text(content)
    for path, content in plan.creates:
        if content is None:
            path.mkdir(parents=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    for source, target in plan.moves:
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
    for path in plan.deletes:
        trash(path)


def move_targets(files: ConfigFiles, path: Path, device: Path) -> List[Path]:
    """:return: the folders a file or folder can be moved to: the common folder and the device folder with their subfolders"""
    path = path.resolve()
    folders = [files.common, device.resolve()]
    if path.suffix in _VARIABLE_SUFFIXES:
        folders.insert(0, files.root)
    result = []
    for folder in folders:
        candidates = [folder] if folder == files.root else [folder, *sorted(p for p in folder.rglob("*") if p.is_dir())]
        result.extend(
            candidate.resolve()
            for candidate in candidates
            if not any(part.startswith(".") for part in candidate.relative_to(files.root).parts)
            and candidate != path.parent
            and not candidate.is_relative_to(path)
        )
    return result


# --- internals ---


def _shown(files: ConfigFiles, path: Path) -> str:
    return files.config_path(path) if path.resolve() != files.root else files.root.name


def _check_lengths(files: ConfigFiles, plan: FilePlan, names: Dict[Path, str], note: bool = False):
    """
    A deploy refuses names longer than `PLATE_NAME_MAX` for the files the plate gets: refuse a long name that a file refers
    to (`L:/<name>`, after the plan's edits). A part that is only included is not uploaded, so its name can be long.
    :param names: the new path of a file -> its new plate name
    :param note: say so for a long name of a new .jsonl file, which nothing runs yet
    """
    for path, name in names.items():
        if len(name) <= PLATE_NAME_MAX:
            continue
        pattern = re.compile(r"L:/" + re.escape(name) + r"(?![\w.\-])")
        if any(pattern.search(plan.edits.get(file, file.read_text())) for file in files.files_seeing(path)):
            raise FileOperationError(
                f"On the plate, it would be {name}: {len(name)} characters, and a deploy refuses names longer than "
                f"{PLATE_NAME_MAX} (folders and file names are joined with _). Choose a shorter name."
            )
        if not note or path.suffix != ".jsonl":
            continue
        plan.notes.append(
            f"On the plate, it would be {name}, which is longer than {PLATE_NAME_MAX} characters: fine for a part, but a "
            "deploy refuses it if a .cmd file runs it."
        )


def _moved_files(path: Path, target: Path) -> Dict[Path, Path]:
    """:return: the old path of every file that moves -> its new path"""
    if path.is_file():
        return {path: target}
    return {file.resolve(): target / file.resolve().relative_to(path) for file in path.rglob("*") if file.is_file()}


def _check_collisions(files: ConfigFiles, new_names: Dict[Path, str], leaving: Set[Path]):
    """:param new_names: new path -> its plate name :param leaving: the files that get another name"""
    for device in files.device_dirs():
        existing = [
            file
            for file in [*_files(files.common, _PLATE_SUFFIXES), *_files(device, _PLATE_SUFFIXES)]
            if file not in leaving
        ]
        taken = files.names_of_device(device, existing)
        for path, name in new_names.items():
            if (files.area_of(path) in (files.common, device)) and name in taken:
                raise FileOperationError(
                    f"{device.name} already has a file named {name} on the plate (folders and file names are joined with _)."
                )


def _check_pages_config(files: ConfigFiles, renames: Dict[Path, Tuple[str, str]]):
    """`hasp.pages` in the config.json of a device names a page file: config.json is not changed (it holds passwords)."""
    for device in files.device_dirs():
        config = device / CONFIG_FILE_NAME
        if not config.is_file():
            continue
        try:
            pages = json.loads(config.read_text()).get("hasp", {}).get("pages", "")
        except ValueError:
            continue
        name = str(pages).removeprefix("L:").removeprefix("/")
        if any(old_name == name for old_name, _ in renames.values()):
            raise FileOperationError(f"hasp.pages in the config.json of {device.name} names {name}: change it there first.")


def _add_reference_edits(
    files: ConfigFiles, plan: FilePlan, renames: Dict[Path, Tuple[str, str]], moved: Dict[Path, Path]
):
    """Change `L:/<old name>` to `L:/<new name>` in the files that see the renamed files."""
    seeing: Set[Path] = set()
    for old in renames:
        seeing.update(files.files_seeing(old))
    by_name = {old_name: new_name for old_name, new_name in renames.values()}
    pattern = re.compile(r"L:/(" + "|".join(re.escape(name) for name in by_name) + r")(?![\w.\-])")
    changed = []
    for file in sorted(seeing):
        content = plan.edits.get(file, file.read_text())
        new_content = pattern.sub(lambda match: f"L:/{by_name[match.group(1)]}", content)
        if new_content != content:
            plan.edits[file] = new_content
            changed.append(moved.get(file, file))
    if changed:
        plan.notes.append(f"Changes the references (L:/...) in: {', '.join(files.config_path(file) for file in changed)}.")


def _add_include_edits(files: ConfigFiles, plan: FilePlan, moved: Dict[Path, Path]):
    """Change the paths of the `!include`s that include moved .jsonl files."""
    paths = {files.config_path(old): files.config_path(new) for old, new in moved.items() if old.suffix == ".jsonl"}
    if not paths:
        return
    pattern = re.compile(r'("!include"\s*:\s*")(' + "|".join(re.escape(path) for path in paths) + r')(")')
    changed = []
    for file in files.jsonl_files():
        content = plan.edits.get(file, file.read_text())
        new_content = pattern.sub(lambda match: match.group(1) + paths[match.group(2)] + match.group(3), content)
        if new_content != content:
            plan.edits[file] = new_content
            changed.append(moved.get(file, file))
    if changed:
        plan.notes.append(f"Changes the !include paths in: {', '.join(files.config_path(file) for file in changed)}.")


def _include_references(files: ConfigFiles, deleted: Set[Path]) -> List[FileReference]:
    """:return: the `!include`s outside of `deleted` that include one of them"""
    paths = {files.config_path(path) for path in deleted if path.suffix == ".jsonl"}
    if not paths:
        return []
    pattern = re.compile(r'"!include"\s*:\s*"(' + "|".join(re.escape(path) for path in paths) + r')"')
    return [
        reference
        for file in files.jsonl_files()
        if file not in deleted
        for reference in _lines_matching(files, file, file.read_text(), pattern)
    ]


def _lines_matching(files: ConfigFiles, file: Path, content: str, pattern: re.Pattern) -> List[FileReference]:
    return [
        _reference(files, file, number, line)
        for number, line in enumerate(content.splitlines(), start=1)
        if pattern.search(line)
    ]


def _reference(files: ConfigFiles, file: Path, line: int, text: str) -> FileReference:
    return FileReference(file, line, text.strip(), f"{files.config_path(file)}:{line}")


def _image_references(files: ConfigFiles, deleted: Set[Path]) -> Set[Path]:
    images = [path for path in deleted if path.suffix in (".png", ".bin")]
    result = set()
    for image in images:
        name = files.plate_name(image)
        pattern = re.compile(r"L:/" + re.escape(name) + r"(?![\w.\-])")
        result.update(file for file in files.files_seeing(image) if file not in deleted and pattern.search(file.read_text()))
    return result


def _check_run_references(files: ConfigFiles, plan: FilePlan, moved: Dict[Path, Path], deleted: Set[Path]):
    """
    Refuse the plan if a .cmd file of a device would run a .jsonl or .cmd file that it doesn't have afterwards (and had
    before): the device couldn't be loaded anymore.
    """
    devices: List[str] = []
    references: List[FileReference] = []
    for device in files.device_dirs():
        before_files = [*_files(files.common, _PLATE_SUFFIXES), *_files(device, _PLATE_SUFFIXES)]
        after_files = [moved.get(file, file) for file in before_files if file not in deleted]
        after_files = [file for file in after_files if files.area_of(file) in (files.common, device)]
        before, after = files.names_of_device(device, before_files), files.names_of_device(device, after_files)
        for file in before_files:
            if file.suffix != ".cmd" or file in deleted:
                continue
            new_path = moved.get(file, file)
            if files.area_of(new_path) not in (files.common, device):
                continue
            old_references = set(_RUN_REFERENCE.findall(file.read_text()))
            new_references = set(_RUN_REFERENCE.findall(plan.edits.get(file, file.read_text())))
            # a reference that worked before, or one that the plan wrote
            broken = sorted(
                name for name in new_references if name not in after and (name in before or name not in old_references)
            )
            if not broken:
                continue
            if device.name not in devices:
                devices.append(device.name)
            # the plan doesn't change the number of lines: find them in its text, show them as they are on disk
            disk_lines = file.read_text().splitlines()
            pattern = re.compile(r"L:/(" + "|".join(re.escape(name) for name in broken) + r")(?![\w.\-])")
            for reference in _lines_matching(files, file, plan.edits.get(file, file.read_text()), pattern):
                if all((reference.file, reference.line) != (other.file, other.line) for other in references):
                    references.append(_reference(files, file, reference.line, disk_lines[reference.line - 1]))
    if references:
        names = devices[0] if len(devices) == 1 else ", ".join(devices[:-1]) + " and " + devices[-1]
        lines = "This line runs" if len(references) == 1 else "These lines run"
        raise FileOperationError(
            f"{'The device' if len(devices) == 1 else 'The devices'} {names} couldn't load "
            f"{'its' if len(devices) == 1 else 'their'} pages anymore.",
            references,
            explanation=f"{lines} a file that {names} wouldn't find anymore:",
            advice=f"Change or remove {'it' if len(references) == 1 else 'them'} first.",
        )
