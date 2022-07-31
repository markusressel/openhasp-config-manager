import json
import re
from typing import List, Dict

from openhasp_config_manager.model import Config, Component


class JsonlObjectProcessor:
    PERCENTAGE_REGEX_PATTERN = re.compile(r"^\d+(\.\d+)?%$")

    def process(self, input: Dict, config: Config) -> Dict:
        for key, value in input.items():
            if isinstance(value, str) and re.match(self.PERCENTAGE_REGEX_PATTERN, value):
                numeric_value = self._parse_percentage(value)

                total_width = config.openhasp_config_manager.device.screen.width
                total_height = config.openhasp_config_manager.device.screen.height

                # switch width and height values if screen is rotated an odd amount of times
                if config.gui.rotate % 2 == 1:
                    t = total_width
                    total_width = total_height
                    total_height = t

                if key in ["x", "w"]:
                    total = total_width
                else:
                    total = total_height

                input[key] = self._percentage_of(numeric_value, total)

        return input

    @staticmethod
    def _percentage_of(percentage: float, total: int) -> int:
        """
        :param percentage: 0..100
        :param total: value for a percentage of 100
        :return: value according to input
        """
        return int((percentage * total) / 100)

    @staticmethod
    def _parse_percentage(value: str) -> float:
        return float(str(value).replace('%', ''))


class DeviceProcessor:
    """
    A device specific processor, used to transform any templates
    present within the configuration files.
    """

    def __init__(self, config: Config, jsonl_object_processor: JsonlObjectProcessor):
        self._device_config = config
        self._file_object_map: Dict[str: dict] = {}
        self._id_object_map: Dict[str: dict] = {}
        self._others: List[Component] = []

        self._jsonl_object_processor = jsonl_object_processor

    def add_other(self, component: Component):
        self._others.append(component)

    def add_jsonl(self, component: Component):
        parts = self._split_jsonl_objects(component.content)

        file_object_map = {}
        for part in parts:
            loaded = json.loads(part)

            object_key = f"p{loaded.get('page', '0')}b{loaded.get('id', '0')}"

            if object_key in self._id_object_map:
                print(f"WARNING: duplicate object key detected: {object_key}")

            file_object_map[object_key] = loaded
            self._id_object_map[object_key] = loaded

    def normalize(self, component: Component) -> str:
        if component.type == "jsonl":
            return self._normalize_jsonl(self._device_config, component)
        else:
            # no changes necessary
            return component.content

    def _normalize_jsonl(self, config: Config, component: Component) -> str:
        normalized_objects: List[str] = []

        objects = self._split_jsonl_objects(component.content)
        for ob in objects:
            p = self._normalize_jsonl_content(config, component, ob)
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

    def _normalize_jsonl_content(self, config: Config, component: Component, content: str):
        parsed = json.loads(content)

        # for key, object in file_object_map.items():

        processed = self._jsonl_object_processor.process(parsed, config)
        return json.dumps(processed, indent=None)
