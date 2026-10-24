import json
from pathlib import Path
from typing import List, Dict, Any, Optional

import orjson

from openhasp_config_manager.openhasp_client.model.component import (
    Component,
    JsonlComponent,
    CmdComponent,
    TextComponent,
    RawComponent,
)
from openhasp_config_manager.openhasp_client.model.configuration.config import Config
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.jsonl import JsonlObjectProcessor
from openhasp_config_manager.processing.preprocessor.jsonl_preprocessor import JsonlPreProcessor
from openhasp_config_manager.processing.template_rendering import render_dict_recursive, render_template
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.util import merge_dict_recursive


class DeviceProcessor:
    """
    A device specific processor, used to transform any templates
    present within the configuration files.
    """

    def __init__(
        self,
        device: Device,
        jsonl_object_processors: List[JsonlObjectProcessor],
        variable_manager: VariableManager,
    ):
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

    def parse_jsonl_objects(self, component: JsonlComponent) -> List[Dict[str, Any]]:
        """
        Parses the objects of a jsonl component as they are written in the file: comments removed, templates not rendered.
        :param component: the component
        :return: the source objects, in the order of the file
        """
        try:
            return [
                orjson.loads(self._jsonl_preprocessor.cleanup_object_for_json_parsing(ob))
                for ob in self._jsonl_preprocessor.split_jsonl_objects(component.content)
            ]
        except ValueError as ex:
            raise ValueError(f"Invalid JSONL in {component.path}: {ex}") from ex

    def jsonl_template_variables(
        self, component: JsonlComponent, draft_objects: Optional[Dict[Path, List[Dict[str, Any]]]] = None
    ) -> Dict[str, Any]:
        """
        :param component: the component, which must have been added to this processor
        :param draft_objects: component path -> its source objects (see parse_jsonl_objects), to use instead of the
            objects in the files of those components
        :return: the variables the templates of the component's objects are rendered with
        """
        return self._compute_jsonl_template_variables(self._device, component, draft_objects)

    def render_jsonl_object(self, source_object: Dict[str, Any], template_vars: Dict[str, Any]) -> Dict[str, Any]:
        """
        Renders one source object like a deployment does: its templates, then the object processors
        (percentages, value types, theme defaults).
        :param source_object: the object as written in the file (see parse_jsonl_objects), it is not modified
        :param template_vars: the variables of its component (see jsonl_template_variables)
        :return: the rendered object
        """
        normalized_object = {}
        for key, value in source_object.items():
            if isinstance(value, str):
                normalized_object[key] = render_template(value, template_vars)
            else:
                normalized_object[key] = value

        processed = normalized_object
        for processor in self._jsonl_object_processors:
            processed = processor.process(processed, self._device.config, template_vars)
        return processed

    def _normalize_jsonl(self, config: Config, component: JsonlComponent, template_vars: Dict[str, any]) -> str:
        return "\n".join(
            json.dumps(self.render_jsonl_object(source_object, template_vars), indent=None)
            for source_object in self.parse_jsonl_objects(component)
        )

    def _normalize_cmd(self, _device_config, component: CmdComponent, template_vars: Dict[str, any]) -> str:
        return render_template(component.content, template_vars)

    def _compute_jsonl_template_variables(
        self, device: Device, component: Component, draft_objects: Optional[Dict[Path, List[Dict[str, Any]]]] = None
    ) -> Dict[str, Any]:
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

            component_template_vars = self._variable_manager.get_vars(c.path)
            component_template_vars["device"] = self._device.config.openhasp_config_manager.device
            if "/common/" in str(c.path):
                # for common components, also include device specific, top-level variables
                device_vars = self._variable_manager.get_vars(device.path)
                component_template_vars = merge_dict_recursive(component_template_vars, device_vars)

            if draft_objects is not None and c.path in draft_objects:
                c_result = self._object_map(draft_objects[c.path])
            else:
                c_result = self._object_map(self.parse_jsonl_objects(c))
            merged_template_variables = merge_dict_recursive(result, component_template_vars)
            merged_template_variables = merge_dict_recursive(merged_template_variables, component_template_vars)

            rendered_template_vars = render_dict_recursive(
                input=c_result, template_vars=merge_dict_recursive(merged_template_variables, c_result)
            )
            rendered_template_vars = merge_dict_recursive(rendered_template_vars, merged_template_variables)

            result = merge_dict_recursive(result, rendered_template_vars)

        if result is None:
            raise AssertionError("Unexpected None value")
        return result

    def _object_map(self, source_objects: List[Dict[str, Any]]) -> Dict[str, dict]:
        """
        :return: "p<page>b<id>" -> the source object
        """
        return {self._compute_object_key(source_object): source_object for source_object in source_objects}

    @staticmethod
    def _compute_object_key(jsonl_object: Dict) -> str:
        return f"p{jsonl_object.get('page', '0')}b{jsonl_object.get('id', '0')}"
