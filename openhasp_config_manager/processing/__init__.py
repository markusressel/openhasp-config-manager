import json
import re
from pathlib import Path
from typing import List, Dict

from jinja2 import Template

from openhasp_config_manager.model import Config, Component, Device
from openhasp_config_manager.processing.jsonl import JsonlObjectProcessor
from openhasp_config_manager.processing.util import render_dict_recursively
from openhasp_config_manager.processing.variables import VariableManager


class DeviceProcessor:
    """
    A device specific processor, used to transform any templates
    present within the configuration files.
    """

    def __init__(self, device: Device, jsonl_object_processors: List[JsonlObjectProcessor],
                 variable_manager: VariableManager):
        self._device = device

        self._id_object_map: Dict[str, dict] = {}
        self._others: List[Component] = []

        self._template_vars: Dict[str, any] = {}

        self._jsonl_object_processors = jsonl_object_processors
        self._variable_manager = variable_manager

    def add_other(self, component: Component):
        self._others.append(component)

    def add_jsonl(self, component: Component):
        parts = self._split_jsonl_objects(component.content)

        for part in parts:
            loaded = json.loads(part)

            object_key = f"p{loaded.get('page', '0')}b{loaded.get('id', '0')}"
            # TODO: this global map doesn't work if templates are used, it needs to be evaluated
            # for each context, so in this case the sub-path that the jsonl is located in
            # Or: the any object key (page & id fields) templates must be rendered before creating this map
            self._id_object_map[object_key] = loaded

    def normalize(self, component: Component) -> str:
        self._template_vars = self._compute_template_variables(component.path)

        if component.type == "jsonl":
            return self._normalize_jsonl(self._device.config, component)
        if component.type == "cmd":
            return self._normalize_cmd(self._device.config, component)
        else:
            # no changes necessary
            return component.content

    def _normalize_jsonl(self, config: Config, component: Component) -> str:
        normalized_objects: List[str] = []

        objects = self._split_jsonl_objects(component.content)
        for ob in objects:
            p = self._normalize_jsonl_object(config, component, ob)
            normalized_objects.append(p)

        return "\n".join(normalized_objects)

    @staticmethod
    def _split_jsonl_objects(original_content: str) -> List[str]:
        pattern_to_find_beginning_of_objects = re.compile(r'^(?!\n)\s*(?=\{)', re.RegexFlag.MULTILINE)
        parts = pattern_to_find_beginning_of_objects.split(original_content)

        result = []
        for part in parts:
            part = part.strip()

            # edge case for first match
            if "}" not in part:
                continue

            # ignore lines starting with "//"
            part = "\n".join([line for line in part.splitlines() if not line.strip().startswith("//")])

            # ignore everything after the last closing bracket
            part = part.rsplit("}", maxsplit=1)[0] + "}"

            result.append(part)

        return result

    def _normalize_jsonl_object(self, config: Config, component: Component, ob: str) -> str:
        parsed = json.loads(ob)

        normalized_object = {}
        for key, value in parsed.items():
            if isinstance(value, str):
                template = Template(value)
                normalized_object[key] = template.render(self._template_vars)
            else:
                normalized_object[key] = value

        processed = normalized_object
        for processor in self._jsonl_object_processors:
            processed = processor.process(processed, config)

        return json.dumps(processed, indent=None)

    def _normalize_cmd(self, _device_config, component) -> str:
        template = Template(component.content)
        return template.render(self._template_vars)

    def _compute_template_variables(self, path: Path) -> dict:
        """
        Computes a map of "variable" -> "evaluated value in the given path context" for the given path.
        :param path: the path to use as a context for evaluating template variables
        :return: map of "variable" -> "evaluated value in the given path context"
        """
        result = {}

        # device specific variables
        result["device"] = self._device.config.openhasp_config_manager.device

        # object specific variables
        for key, obj in self._id_object_map.items():
            result[key] = obj

        result |= self._variable_manager.get_vars(path)

        rendered = render_dict_recursively(input=result, template_vars=result)

        return rendered
