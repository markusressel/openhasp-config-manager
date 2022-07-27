import json
import re
from typing import List, Dict

from openhasp_config_manager.model import Config, Device


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


class Processor:

    def __init__(self, jsonl_object_processor: JsonlObjectProcessor):
        self._object_map: Dict[str: dict] = {}
        self._jsonl_object_processor = jsonl_object_processor

    def process_jsonl(self, device: Device, original_content: str) -> str:
        return self._normalize_jsonl(device.config, original_content)

    def _normalize_jsonl(self, config: Config, original_content: str) -> str:
        parts = self._split_jsonl_objects(original_content)
        normalized_parts: List[str] = []
        for part in parts:
            loaded = json.loads(part)

            processed = self._jsonl_object_processor.process(loaded, config)

            object_key = f"p{processed.get('page', '0')}b{processed.get('id', '0')}"

            if object_key in self._object_map:
                print(f"WARNING: duplicate object key detected: {object_key}")

            self._object_map[object_key] = processed

            p = json.dumps(processed, indent=None)

            normalized_parts.append(p)

        return "\n".join(normalized_parts)

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
