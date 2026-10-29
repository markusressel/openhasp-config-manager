import contextlib
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openhasp_config_manager.gui.domain.draft.files import BOOT_CMD, load_analyzed_device
from openhasp_config_manager.gui.domain.gui_state import relative
from openhasp_config_manager.gui.domain.file_tree import used_files
from openhasp_config_manager.gui.domain.draft.page_objects import get_page_objects
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.domain.problems import Severity, find_problems, object_name
from openhasp_config_manager.gui.domain.variables.unused import find_unused_variables
from openhasp_config_manager.gui.domain.variables.usages import DeviceFiles, VariableUsages
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.jsonl.includes import (
    IncludeExpansionError,
    IncludeStep,
    IncludedObjectError,
    describe_step,
)


@dataclass(frozen=True)
class Issue:
    severity: Severity
    message: str
    device: Optional[str] = None
    # relative to the config directory
    file: Optional[str] = None
    line: Optional[int] = None
    object: Optional[str] = None
    # for a problem in a file that an `!include` includes: the directives that lead to it ("file:line", with the loop values of
    # the instance), outermost first
    included_at: Optional[Tuple[str, ...]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "severity": self.severity.value}

    def __str__(self) -> str:
        location = ":".join(str(part) for part in (self.file, self.line) if part is not None)
        message = self.message + (f" (included at {' > '.join(self.included_at)})" if self.included_at else "")
        parts = [f"{location}:" if location else None, f"{self.severity.value}:", message]
        if self.device:
            parts.append(f"[{self.device}]")
        return " ".join(part for part in parts if part)


def check_config(config_manager: ConfigManager, device_name: Optional[str] = None) -> Tuple[List[str], List[Issue]]:
    """
    Check the config directory without writing or sending anything: what a deployment would fail on (files that can't be
    processed, validation), and what is wrong with the pages (the problems the GUI shows, unknown template variables).
    Variables that no device uses are reported as hints, but only when all devices are checked (a device alone can't tell).
    Console output of the analysis goes to stderr.
    :param device_name: check only this device
    :return: the names of the checked devices, and what is wrong, errors first
    """
    config_dir = Path(config_manager.cfg_root).resolve()
    with contextlib.redirect_stdout(sys.stderr):
        try:
            devices = sorted(config_manager.analyze(), key=lambda device: device.name)
        except Exception as ex:
            return [], [Issue(Severity.ERROR, f"Can't analyze the config directory: {ex}")]
        if device_name is not None:
            devices = [device for device in devices if device.name == device_name]
            if not devices:
                return [], [Issue(Severity.ERROR, f"No device matches the filter: {device_name}")]

        issues: List[Issue] = []
        for device in devices:
            issues += _check_device(config_manager, config_dir, devices, device)
        if device_name is None:
            issues += _check_unused_variables(config_dir, devices)
    return [device.name for device in devices], sorted(issues, key=lambda issue: issue.severity != Severity.ERROR)


def _check_unused_variables(config_dir: Path, devices: List[Device]) -> List[Issue]:
    """The variables of the YAML files that no file of any device uses (see `VariableUsages`)."""
    try:
        usages = VariableUsages(
            config_dir, [DeviceFiles(d.path, list(used_files(d.cmd, d.jsonl, config_dir))) for d in devices]
        )
        unused = find_unused_variables(usages)
    except Exception as ex:
        return [Issue(Severity.ERROR, f"Can't look for unused variables: {ex}")]
    return [
        Issue(issue.severity, issue.message, file=relative(path, config_dir), line=issue.line)
        for path, found in sorted(unused.items())
        for issue in found.issues
    ]


def _check_device(config_manager: ConfigManager, config_dir: Path, devices: List[Device], device: Device) -> List[Issue]:
    issues = _check_files(config_manager, config_dir, device)
    if any(component.name == BOOT_CMD for component in device.cmd):
        try:
            issues += _check_pages(config_manager, config_dir, devices, device)
        except Exception as ex:
            issues.append(Issue(Severity.ERROR, f"Can't load the pages: {ex}", device=device.name))
    return issues


def _check_files(config_manager: ConfigManager, config_dir: Path, device: Device) -> List[Issue]:
    """The checks of a deployment, for every file: processing and validation."""
    try:
        processor = config_manager.create_device_processor(device)
        validator = config_manager.create_device_validator(device)
        components = config_manager.find_relevant_components(device)
    except Exception as ex:
        return [Issue(Severity.ERROR, f"Can't read the device: {ex}", device=device.name)]

    issues = []
    for component in components:
        file = relative(component.path, config_dir)
        try:
            output = processor.normalize(device, component)
        except IncludeExpansionError as ex:
            for error in ex.errors:
                message = f"Can't process the file: {error.message}"
                issues.append(_included_issue(message, device, config_dir, error.file, error.line, error.includes))
            continue
        except IncludedObjectError as ex:
            message = f"Can't process the file: {ex.reason}"
            origin = ex.origin
            issues.append(_included_issue(message, device, config_dir, origin.file, origin.line, origin.includes))
            continue
        except Exception as ex:
            issues.append(Issue(Severity.ERROR, f"Can't process the file: {ex}", device=device.name, file=file))
            continue
        try:
            validator.validate(component, output)
        except Exception as ex:
            issues.append(Issue(Severity.ERROR, f"Validation failed: {ex}", device=device.name, file=file))
    return issues


def _included_issue(
    message: str, device: Device, config_dir: Path, file: Path, line: int, includes: Tuple[IncludeStep, ...]
) -> Issue:
    """:return: an error at a place in a file that is processed, or in a part it includes (`includes`)"""
    included_at = tuple(describe_step(step, config_dir) for step in includes) or None
    return Issue(
        Severity.ERROR,
        message,
        device=device.name,
        file=relative(file, config_dir),
        line=line,
        included_at=included_at,
    )


def _check_pages(config_manager: ConfigManager, config_dir: Path, devices: List[Device], device: Device) -> List[Issue]:
    """The pages the way the GUI shows them: its problems, and template variables that don't exist."""
    loaded = load_analyzed_device(config_manager, devices, device)
    session = PlateSession(device=loaded.device)
    session.load(loaded.components, loaded.renderer)

    issues = []
    screen = device.config.openhasp_config_manager.device.screen
    pages = sorted({obj["page"] for objects in session.working_objects.values() for obj in objects if "page" in obj})
    for page in pages:
        problems = find_problems(get_page_objects(session.working_objects, index=page), screen.width, screen.height)
        for problem in problems:
            issues.append(_object_issue(session, problem.obj, problem.severity, problem.message, device, config_dir))

    for objects in session.working_objects.values():
        for obj in objects:
            # a deployment writes unknown variables as they are: the plate would show "{{ name }}"
            for key, value in session.source_of(obj).items():
                error = session.check_template(obj, value) if isinstance(value, str) and "{{" in value else None
                if error:
                    message = f"{object_name(obj)}: {key}: {error}"
                    issues.append(_object_issue(session, obj, Severity.WARNING, message, device, config_dir))
    return issues


def _object_issue(
    session: PlateSession, obj: Dict, severity: Severity, message: str, device: Device, config_dir: Path
) -> Issue:
    origin = session.origin_of(obj)
    if origin is not None:
        # the text to change is in the part
        included_at = tuple(describe_step(step, config_dir) for step in origin.includes)
        return Issue(
            severity,
            message,
            device=device.name,
            file=relative(origin.file, config_dir),
            line=origin.line,
            object=object_name(obj),
            included_at=included_at,
        )
    return Issue(
        severity,
        message,
        device=device.name,
        file=relative(session.component_of(obj).path, config_dir),
        line=session.line_of(obj),
        object=object_name(obj),
    )
