import json
from typing import List, Dict, Any

import orjson

from openhasp_config_manager.openhasp_client.model.component import Component, JsonlComponent, CmdComponent, \
    TextComponent, RawComponent
from openhasp_config_manager.openhasp_client.model.configuration.config import Config
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.jsonl import JsonlObjectProcessor
from openhasp_config_manager.processing.preprocessor.jsonl_preprocessor import JsonlPreProcessor
from openhasp_config_manager.processing.template_rendering import render_dict_recursive, _render_template
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.util import merge_dict_recursive


class DeviceProcessor:
    """
    A device specific processor, used to transform any templates
    present within the configuration files.
    """

    def __init__(self, device: Device, jsonl_object_processors: List[JsonlObjectProcessor],
                 variable_manager: VariableManager):
        self._device = device

        self._jsonl_components: List[JsonlComponent] = []
        self._others: List[Component] = []

        self._jsonl_preprocessor = JsonlPreProcessor()
        self._jsonl_object_processors = jsonl_object_processors
        self._variable_manager = variable_manager

    def add_component(self, component: Component):
        if isinstance(component, JsonlComponent):
            self._add_jsonl(component)
        else:
            self._add_other(component)

    def _add_other(self, component: Component):
        self._others.append(component)

    def _add_jsonl(self, component: JsonlComponent):
        self._jsonl_components.append(component)

    def normalize(self, device: Device, component: Component) -> str | bytes:
        if isinstance(component, JsonlComponent):
            template_vars: Dict[str, any] = self._compute_jsonl_template_variables(device, component)
            return self._normalize_jsonl(self._device.config, component, template_vars)
        elif isinstance(component, CmdComponent):
            template_vars: Dict[str, any] = {}
            return self._normalize_cmd(self._device.config, component, template_vars)
        elif isinstance(component, TextComponent):
            # no changes necessary
            return component.content
        elif isinstance(component, RawComponent):
            # no changes necessary
            return component.content
        elif isinstance(component, Component):
            raise NotImplementedError(f"Unknown component type: {component.type}")
        else:
            raise AssertionError(f"Received unexpected input: {component}")

    def _normalize_jsonl(self, config: Config, component: JsonlComponent, template_vars: Dict[str, any]) -> str:
        normalized_objects: List[str] = []

        objects = self._jsonl_preprocessor.split_jsonl_objects(component.content)
        for ob in objects:
            preprocessed = self._jsonl_preprocessor.cleanup_object_for_json_parsing(ob)
            p = self._normalize_jsonl_object(config, component, preprocessed, template_vars)
            normalized_objects.append(p)

        return "\n".join(normalized_objects)

    def _normalize_jsonl_object(
        self, config: Config, component: JsonlComponent, ob: str, template_vars: Dict[str, any]
    ) -> str:
        parsed = orjson.loads(ob)

        normalized_object = {}
        for key, value in parsed.items():
            if isinstance(value, str):
                rendered_value = _render_template(value, template_vars)
                normalized_object[key] = rendered_value
            else:
                normalized_object[key] = value

        processed = normalized_object
        for processor in self._jsonl_object_processors:
            processed = processor.process(processed, config, template_vars)

        return json.dumps(processed, indent=None)

    def _normalize_cmd(self, _device_config, component: CmdComponent, template_vars: Dict[str, any]) -> str:
        return _render_template(component.content, template_vars)

    def _compute_jsonl_template_variables(self, device: Device, component: Component) -> Dict[str, Any]:
        """
        Computes a map of "variable" -> "evaluated value in the given path context" for the given component.

        :param component: the component to use as a context for evaluating template variables
        :return: map of "variable" -> "evaluated value in the given path context"
        """
        result = {}

        # object specific variables for all components that the processor currently knows about
        sorted_components = list(sorted(self._jsonl_components, key=lambda x: x == component))
        assert sorted_components[-1] == component
        for c in sorted_components:
            jsonl_objects = self._jsonl_preprocessor.split_jsonl_objects(c.content)

            component_template_vars = self._variable_manager.get_vars(c.path)
            component_template_vars["device"] = self._device.config.openhasp_config_manager.device
            if "/common/" in str(c.path):
                # for common components, also include device specific, top-level variables
                device_vars = self._variable_manager.get_vars(device.path)
                component_template_vars = merge_dict_recursive(component_template_vars, device_vars)

            c_result = self._compute_object_map(jsonl_objects)
            merged_template_variables = merge_dict_recursive(result, component_template_vars)
            merged_template_variables = merge_dict_recursive(merged_template_variables, component_template_vars)

            rendered_template_vars = render_dict_recursive(
                input=c_result,
                template_vars=merge_dict_recursive(merged_template_variables, c_result)
            )
            rendered_template_vars = merge_dict_recursive(rendered_template_vars, merged_template_variables)

            result = merge_dict_recursive(result, rendered_template_vars)

        if result is None:
            raise AssertionError("Unexpected None value")
        return result

    def _compute_object_map(self, jsonl_objects: List[str]) -> Dict[str, dict]:
        """
        :param jsonl_objects:
        :return: a map
        """
        result = {}
        for o in jsonl_objects:
            o = self._jsonl_preprocessor.cleanup_object_for_json_parsing(o)
            parsed_object = orjson.loads(o)
            object_key = self._compute_object_key(parsed_object)
            result[object_key] = parsed_object
        return result

    @staticmethod
    def _compute_object_key(jsonl_object: Dict) -> str:
        return f"p{jsonl_object.get('page', '0')}b{jsonl_object.get('id', '0')}"
