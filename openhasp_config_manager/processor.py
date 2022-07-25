import json
import re
from typing import List, Dict

from openhasp_config_manager.model import Config


class JsonlObjectProcessor:
    PERCENTAGE_REGEX_PATTERN = re.compile(r"^\d+%$")

    def __init__(self, configuration: Config):
        self.config = configuration

    def process(self, input: Dict) -> Dict:
        for key, value in input.items():
            if isinstance(value, str) and re.match(self.PERCENTAGE_REGEX_PATTERN, value):
                numeric_value = self._parse_percentage(value)

                if key in ["x", "w"]:
                    total = self.config.openhasp_config_manager.device.screen.width
                else:
                    total = self.config.openhasp_config_manager.device.screen.height

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
        self.jsonl_object_processor = jsonl_object_processor

    def process_jsonl(self, original_content: str) -> str:
        return self._normalize_jsonl(original_content)

    def _normalize_jsonl(self, original_content: str) -> str:
        parts = self._split_jsonl_objects(original_content)
        normalized_parts: List[str] = []
        for part in parts:
            loaded = json.loads(part)
            processed = self.jsonl_object_processor.process(loaded)

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
