import json
import re
from pathlib import Path
from typing import List, Dict

import jinja2
from jinja2 import Template

from openhasp_config_manager.model import Config, Component, Device
from openhasp_config_manager.processing.jsonl import JsonlObjectProcessor
from openhasp_config_manager.processing.variables import VariableManager


class DeviceProcessor:
    """
    A device specific processor, used to transform any templates
    present within the configuration files.
    """

    def __init__(self, device: Device, jsonl_object_processor: JsonlObjectProcessor, variable_manager: VariableManager):
        self._device = device

        self._id_object_map: Dict[str, dict] = {}
        self._others: List[Component] = []

        self._template_vars: Dict[str, any] = {}

        self._jsonl_object_processor = jsonl_object_processor
        self._variable_manager = variable_manager

    def add_other(self, component: Component):
        self._others.append(component)

    def add_jsonl(self, component: Component):
        parts = self._split_jsonl_objects(component.content)

        for part in parts:
            loaded = json.loads(part)

            object_key = f"p{loaded.get('page', '0')}b{loaded.get('id', '0')}"
            # FIXME: this global map doesn't work if templates are used, it needs to be evaluated
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

        processed = self._jsonl_object_processor.process(normalized_object, config)
        return json.dumps(processed, indent=None)

    def _normalize_cmd(self, _device_config, component) -> str:
        template = Template(component.content)
        return template.render(self._template_vars)

    def _compute_template_variables(self, path: Path) -> dict:
        result = {}

        # device specific variables
        result["device"] = self._device.config.openhasp_config_manager.device

        # object specific variables
        for key, obj in self._id_object_map.items():
            result[key] = obj

        result |= self._variable_manager.get_vars(path)

        rendered = self._render_dict_recursively(input=result, template_vars=result)

        return rendered

    def _render_dict_recursively(
            self,
            input: Dict,
            template_vars: Dict,
            result_key_path: List[str] = None,
    ) -> Dict[str, any]:
        if result_key_path is None:
            result_key_path = []

        from jinja2.meta import find_undeclared_variables
        env = jinja2.Environment(undefined=jinja2.DebugUndefined)

        result = {}

        finished = False
        progress = 0
        pending = []
        last_pending = None
        while not finished:
            finished = True
            keys = list(input.keys())
            for key in keys:
                value = input[key]
                # key
                try:
                    template = env.from_string(key)
                    rendered_key = template.render(template_vars)
                    ast = env.parse(rendered_key)
                    key_undefined = find_undeclared_variables(ast)
                except Exception as ex:
                    print(f"Undefined key: {key_undefined}, value: {key}")
                    key_undefined = True

                # value
                value_undefined = False
                rendered_value = value
                if isinstance(value, dict) and not key_undefined:
                    rendered_value = self._render_dict_recursively(
                        value,
                        template_vars,
                        result_key_path + [rendered_key]
                    )
                elif isinstance(value, str):
                    try:
                        template = env.from_string(value)
                        rendered_value = template.render(template_vars)
                        ast = env.parse(rendered_value)
                        value_undefined = find_undeclared_variables(ast)
                    except Exception as ex:
                        # print(f"Undefined value: {value_undefined}, value: {value}")
                        value_undefined = True

                if key_undefined:
                    pending.append(key)
                if value_undefined:
                    pending.append(f"{key}__value")

                if key_undefined or value_undefined:
                    # still has undefined keys
                    # print(f"Undefined keys: {key_undefined}, Undefined values: {value_undefined}")
                    finished = False
                else:
                    # add it to the template_vars data at the correct location
                    # which allows later iterations to render the template correctly
                    tmp = template_vars
                    for idx, p in enumerate(result_key_path):
                        if p not in tmp.keys():
                            tmp[p] = {}
                        tmp = tmp[p]
                    tmp.pop(key, None)
                    tmp[rendered_key] = rendered_value

                    if rendered_key not in result or result[rendered_key] != rendered_value:
                        progress += 1

                    # create the resulting (sub-)dictionary
                    result[rendered_key] = rendered_value

                    finished = finished and True

            if len(pending) <= 0:
                return result
            elif pending == last_pending:
                # No progression while rendering templates, return as is
                return result
            else:
                last_pending = pending

        return result
