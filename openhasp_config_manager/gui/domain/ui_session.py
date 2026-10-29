import dataclasses
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

T = TypeVar("T")


@dataclass
class DeviceSession:
    """What the user chose in the editor for one device."""

    # the .jsonl file new objects go into, relative to the config directory (e.g. "devices/plate/page.jsonl")
    target_file: Optional[str] = None


@dataclass
class TabSession:
    """A tab of the preview that is opened again on the next start (see `MainWindow._restore_tabs`)."""

    device: str = ""
    # the part of a part tab, relative to the config directory; None for the tab of the pages of the device
    part: Optional[str] = None
    # where the instance of a part tab is included (see `PlateSession.describe_instance`), None for the first one
    instance: Optional[str] = None


@dataclass
class UiSession:
    """
    The state of the editor that is restored on the next start, for one config directory.

    To remember something new, add a field with a default (here or in DeviceSession). Values that are missing in what
    was stored, or that don't fit the field anymore, get the default, so nothing needs to be migrated.
    """

    # the device of the active tab
    selected_device: Optional[str] = None
    # the tabs of the preview, in their order, and the index of the active one
    open_tabs: List[TabSession] = field(default_factory=list)
    active_tab: Optional[int] = None
    # the files open in the text editor and the one shown, relative to the config directory
    open_files: List[str] = field(default_factory=list)
    current_file: Optional[str] = None
    devices: Dict[str, DeviceSession] = field(default_factory=dict)

    def device(self, name: str) -> DeviceSession:
        """:return: the session of a device, created if it has none yet"""
        return self.devices.setdefault(name, DeviceSession())


def to_data(value: Any) -> Any:
    """:return: a dataclass (with nested dataclasses, dicts, lists and plain values) as JSON-compatible data"""
    if dataclasses.is_dataclass(value):
        return {f.name: to_data(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): to_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_data(item) for item in value]
    return value


class _Invalid(Exception):
    pass


def from_data(cls: Type[T], data: Any) -> T:
    """
    :return: a dataclass created from data of `to_data`. Unknown keys are ignored, missing or invalid values get
        the default of their field.
    """
    if not isinstance(data, dict):
        return cls()
    hints = typing.get_type_hints(cls)
    values = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        try:
            values[f.name] = _convert(hints[f.name], data[f.name])
        except _Invalid:
            continue
    return cls(**values)


def _convert(hint: Any, value: Any) -> Any:
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        for arg in args:
            if arg is not type(None):
                try:
                    return _convert(arg, value)
                except _Invalid:
                    continue
        raise _Invalid()
    if dataclasses.is_dataclass(hint):
        if not isinstance(value, dict):
            raise _Invalid()
        return from_data(hint, value)
    if origin is dict:
        if not isinstance(value, dict):
            raise _Invalid()
        result = {}
        for key, item in value.items():
            try:
                result[_convert(args[0], key)] = _convert(args[1], item)
            except _Invalid:
                continue
        return result
    if origin is list:
        if not isinstance(value, list):
            raise _Invalid()
        return [_convert(args[0], item) for item in value]
    if hint is Any:
        return value
    # bool is an int in Python, but not the other way round
    if not isinstance(value, hint) or (hint is int and isinstance(value, bool)):
        raise _Invalid()
    return value
