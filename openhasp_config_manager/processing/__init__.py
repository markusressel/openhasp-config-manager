import json
import re
from typing import List, Dict

from jinja2 import Template

from openhasp_config_manager.model import Config, Component, Device
from openhasp_config_manager.processing.jsonl import JsonlObjectProcessor
from openhasp_config_manager.processing.template_rendering import render_dict_recursive, _render_template
from openhasp_config_manager.processing.variables import VariableManager


class DeviceProcessor:
    """
    A device specific processor, used to transform any templates
    present within the configuration files.
    """

    def __init__(self, device: Device, jsonl_object_processors: List[JsonlObjectProcessor],
                 variable_manager: VariableManager):
        self._device = device

        self._jsonl_components: List[Component] = []
        self._others: List[Component] = []

        self._template_vars: Dict[str, any] = {}

        self._jsonl_object_processors = jsonl_object_processors
        self._variable_manager = variable_manager

    def add_other(self, component: Component):
        self._others.append(component)

    def add_jsonl(self, component: Component):
        self._jsonl_components.append(component)

    def normalize(self, component: Component) -> str:
        self._template_vars = self._compute_template_variables(component)

        if component.type == "jsonl":
            return self._normalize_jsonl(self._device.config, component)
        elif component.type == "cmd":
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
                rendered_value = _render_template(value, self._template_vars)
                normalized_object[key] = rendered_value
            else:
                normalized_object[key] = value

        processed = normalized_object
        for processor in self._jsonl_object_processors:
            processed = processor.process(processed, config)

        return json.dumps(processed, indent=None)

    def _normalize_cmd(self, _device_config, component) -> str:
        template = Template(component.content)
        return template.render(self._template_vars)

    def _compute_template_variables(self, component: Component) -> dict:
        """
        Computes a map of "variable" -> "evaluated value in the given path context" for the given component.

        :param component: the component to use as a context for evaluating template variables
        :return: map of "variable" -> "evaluated value in the given path context"
        """
        result = {}

        # object specific variables for all components that the processor currently knows about
        for c in self._jsonl_components:
            jsonl_objects = self._split_jsonl_objects(c.content)
            c_result = self._variable_manager.get_vars(c.path)
            c_result["device"] = self._device.config.openhasp_config_manager.device
            c_result |= self._compute_object_map(jsonl_objects)
            rendered = render_dict_recursive(input=c_result, template_vars=c_result)
            result |= rendered

        # device specific variables
        result["device"] = self._device.config.openhasp_config_manager.device
        result |= self._variable_manager.get_vars(component.path)
        rendered = render_dict_recursive(input=result, template_vars=result)

        return rendered

    def _compute_object_map(self, jsonl_objects: List[str]) -> Dict[str, dict]:
        """
        :param jsonl_objects:
        :return: a map
        """
        result = {}
        for o in jsonl_objects:
            parsed_object = json.loads(o)
            object_key = self._compute_object_key(parsed_object)
            result[object_key] = parsed_object
        return result

    @staticmethod
    def _compute_object_key(jsonl_object: Dict) -> str:
        return f"p{jsonl_object.get('page', '0')}b{jsonl_object.get('id', '0')}"
