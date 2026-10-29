import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional

from openhasp_config_manager.const import COMMON_FOLDER_NAME
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model import device as config_device
from openhasp_config_manager.openhasp_client.model.configuration.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.configuration.hasp_config import HaspConfig
from openhasp_config_manager.openhasp_client.model.configuration.screen_config import ScreenConfig
from openhasp_config_manager.processing.jsonl.includes import (
    INCLUDE,
    VARS,
    IncludedObjectError,
    IncludeExpansionError,
    ObjectOrigin,
    display_path,
)
from openhasp_config_manager.processing.template_rendering import render_template
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.validation.jsonl import JsonlObjectValidator

# the variable a part gets the index of its page in (`"page": "{{ page_index }}"`), see `ConfigModel.render_part`
PAGE_INDEX = "page_index"

_EMPTY: Mapping[Any, Any] = MappingProxyType({})
_OBJECT_NAME = re.compile(r"p(\d+)b(\d+)")


@dataclass(frozen=True)
class Device:
    """A device of the config directory: what code can use of its `config.json`. Its credentials are not part of it."""

    name: str
    # its folder in `devices/`
    path: Path
    ip: str
    # the size of the screen as the pages see it, i.e. after rotation (like `device.screen` in the templates)
    screen: ScreenConfig
    gui: GuiConfig
    hasp: HaspConfig


@dataclass(frozen=True)
class PartObject:
    """An object of one instance of a part before it is rendered: what the expansion of an `!include` knows of it."""

    page: int
    id: int
    # its type (`obj`), rendered with the variables of the instance; None if it has none
    obj: Optional[str]
    origin: ObjectOrigin


@dataclass(frozen=True)
class RenderedObject:
    """An object of one instance of a part, as a deployment sends it to the plate."""

    jsonl: Mapping[str, Any]
    # the part file and the line of the object, and the `!include`s that lead to it (see `ConfigModel.describe`)
    origin: ObjectOrigin


class ConfigModel:
    """
    The config directory, as one device sees it: its variables and its parts, rendered with the code a deployment uses
    (`ConfigManager`, `DeviceProcessor`, `expand_includes`, the JSONL processors and `JsonlObjectValidator`), so it can't
    render differently.

    The files are read once, by `load()`. After a change of the config directory, load it again.
    """

    def __init__(self, manager: ConfigManager, device: config_device.Device):
        """Use `load()`. :param manager: a manager that analyzed the config directory, `device` one of its devices"""
        self._manager = manager
        self._config_device = device
        self._processor = manager.create_device_processor(device)
        config = device.config.openhasp_config_manager.device
        self.device = Device(
            name=device.name,
            path=device.path,
            ip=config.ip,
            screen=config.screen,
            gui=device.config.gui,
            hasp=device.config.hasp,
        )

    @staticmethod
    def load(config_dir: Path, device: str) -> "ConfigModel":
        """
        :param config_dir: the config directory
        :param device: the name of a device, the name of its folder in `devices/`
        :raises ValueError: if the config directory has no such device
        """
        # nothing is written: the output directory is only needed by the manager
        manager = ConfigManager(Path(config_dir), Path("./nonexistent"), VariableManager(cfg_root=Path(config_dir)))
        devices = manager.analyze()
        found = next((d for d in devices if d.name == device), None)
        if found is None:
            names = ", ".join(sorted(d.name for d in devices))
            raise ValueError(f"Unknown device: {device}, the devices of {config_dir} are: {names}")
        return ConfigModel(manager, found)

    @property
    def config_dir(self) -> Path:
        return self._manager.cfg_root

    def variables(self, path: str = COMMON_FOLDER_NAME) -> Dict[str, Any]:
        """
        The computed variables of a path for this device, like `vars -p <path> -d <device>` prints them, and `device` (the
        `device` the templates see: `ip`, `screen.width`, `screen.height`). For a path in `common/` that is what its files
        see on this device: the variables of its folders and of the device's folder.
        :param path: a file or folder of the config directory, relative to it
        :raises TemplateRenderError: if a variable can't be computed
        :raises ValueError: if the path is in the folder of another device
        """
        variables = self._manager.variables_of_path(Path(self.config_dir, path), self.device.name)
        return {**variables, "device": self._config_device.config.openhasp_config_manager.device}

    def expand_part(self, path: str, *, page: int, vars: Mapping[str, Any] = _EMPTY) -> List[PartObject]:
        """
        The objects of one instance of a part before they are rendered: their page, id and type, which are known from the
        variables of the instance alone (see include-directive.md, "Ids"), so a page can keep their ids free before it
        renders anything. See `render_part` for the arguments.
        :raises IncludeExpansionError: if the `!include` can't be expanded (e.g. the part doesn't exist, ids collide)
        :raises IncludedObjectError: if the type of an object can't be rendered
        """
        expansion = self._processor.expand_sources(self._page_file(page), [self._directive(path, page, vars)])
        if expansion.errors:
            raise IncludeExpansionError(expansion.errors, self.config_dir)
        result = []
        for obj in expansion.objects:
            object_page, object_id = (int(number) for number in _OBJECT_NAME.fullmatch(obj.name).groups())
            obj_type = obj.source.get("obj")
            if isinstance(obj_type, str):
                try:
                    obj_type = render_template(obj_type, obj.scope, strict=True)
                except Exception as ex:
                    raise IncludedObjectError(obj.origin, self.config_dir, str(ex)) from ex
            result.append(PartObject(page=object_page, id=object_id, obj=obj_type, origin=obj.origin))
        return result

    def render_part(
        self,
        path: str,
        *,
        page: int,
        vars: Mapping[str, Any] = _EMPTY,
        objects: Mapping[int, Mapping[str, Any]] = _EMPTY,
    ) -> List[RenderedObject]:
        """
        The objects of one instance of a part, as a deployment sends them for an `!include` of it with these `vars` in a
        file of `common/` on this device: templates rendered, percentages in pixels, the theme (`theme.obj.*`) applied,
        validated.

        The instance sees what an `!include` sees (include-directive.md, "Variables of a part"): the part's defaults, the
        variables of `common/` for the device (see `variables()`), and `vars` with `page_index`. Its object references see
        the objects of the device's files (`pXbY`), except those on `page`, which `objects` replaces: `bY` is one of
        `objects` or of the part itself.

        :param path: the part, relative to the config directory (as in an `!include`)
        :param page: the index of the page of the instance, the variable `page_index` of the part
        :param vars: the variables of the instance, like the `vars` of an `!include` (templates in them are rendered)
        :param objects: the other objects of the page by id, as they are sent to the plate, for the references of the part
            (`b4.x`). Their values are used like those of objects in a file (a text with `{{` is a template).
        :raises IncludeExpansionError: if the `!include` can't be expanded (e.g. the part doesn't exist, ids collide)
        :raises IncludedObjectError: if an object of the part can't be rendered
        :raises AssertionError: if a rendered object is invalid (see `JsonlObjectValidator`)
        """
        sources = [self._page_object(page, obj_id, obj) for obj_id, obj in objects.items()]
        sources.append(self._directive(path, page, vars))
        rendered = self._processor.render_sources(self._page_file(page), sources, replaced_page=page)
        result = [RenderedObject(jsonl=jsonl, origin=obj.origin) for obj, jsonl in rendered if obj.origin.is_included]
        JsonlObjectValidator().validate("\n".join(json.dumps(obj.jsonl) for obj in result))
        return result

    def describe(self, origin: ObjectOrigin) -> str:
        """
        :param origin: the origin of an object of `expand_part` or `render_part`
        :return: where the object is written, from the part of the instance on: the line of each `!include` in a part, then
            the object, e.g. `common/parts/header/header.jsonl:3 > common/parts/header/label.jsonl:2`
        """
        places = [f"{display_path(step.file, self.config_dir)}:{step.line}" for step in origin.includes[1:]]
        return " > ".join([*places, f"{display_path(origin.file, self.config_dir)}:{origin.line}"])

    def _page_file(self, page: int) -> Path:
        """The file the instances of parts are rendered in: a page in `common/`, which doesn't exist."""
        return Path(self.config_dir, COMMON_FOLDER_NAME, f"<code page {page}>.jsonl")

    @staticmethod
    def _directive(path: str, page: int, vars: Mapping[str, Any]) -> Dict[str, Any]:
        if PAGE_INDEX in vars:
            raise ValueError(f"'{PAGE_INDEX}' of a part is its page, given by page=, not in vars")
        return {INCLUDE: path, VARS: {**vars, PAGE_INDEX: page}}

    @staticmethod
    def _page_object(page: int, obj_id: int, obj: Mapping[str, Any]) -> Dict[str, Any]:
        if obj.get("page", page) != page or obj.get("id", obj_id) != obj_id:
            raise ValueError(f"The object p{page}b{obj_id} of the page is p{obj.get('page')}b{obj.get('id')}: {dict(obj)}")
        return {**obj, "page": page, "id": obj_id}
