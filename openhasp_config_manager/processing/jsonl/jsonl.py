import logging
import re
from typing import Dict

from openhasp_config_manager.openhasp_client.model.configuration.config import Config
from openhasp_config_manager.processing.jsonl import JsonlObjectProcessor

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)


class ObjectDimensionsProcessor(JsonlObjectProcessor):
    """
    Used to process .jsonl files to add support for additional features.
    """
    PERCENTAGE_REGEX_PATTERN = re.compile(r"^\d+(\.\d+)?%$")

    def process(
        self, input: Dict, config: Config, template_vars: Dict[str, any]
    ) -> Dict:
        result: Dict[str, any] = {}
        for key, value in input.items():
            if isinstance(value, str) and re.match("[xywh]", key) and re.match(self.PERCENTAGE_REGEX_PATTERN, value):
                numeric_value = self._parse_percentage(value)

                total_width = config.openhasp_config_manager.device.screen.width
                total_height = config.openhasp_config_manager.device.screen.height

                if key in ["x", "w"]:
                    total = total_width
                else:
                    total = total_height

                result[key] = self._percentage_of(numeric_value, total)
            else:
                result[key] = value

        # normalize value types, in case of templates
        for key, value in result.items():
            try:
                match = re.match(
                    "^(page|id|x|y|w|h|text_font|value_font|radius|pad_.+|margin_.+|border_width|min|max|prev|next).*$",
                    string=key,
                )

                if match and isinstance(value, str):
                    result[key] = int(float(value))
            except Exception as ex:
                LOGGER.exception(ex)
                print(f"{key}: {value}: {ex}, {input}")

        return result

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


class ObjectThemeProcessor(JsonlObjectProcessor):
    """
    Used to apply default theming from "theme.obj.*" values
    """

    def process(
        self, input: Dict, config: Config, template_vars: Dict[str, any]
    ) -> Dict:
        obj_key = input.get("obj", None)
        if obj_key is None:
            return input

        theme_values = template_vars.get("theme", {}).get("obj", {}).get(obj_key, {})
        for key, value in theme_values.items():
            if key not in input:
                input[key] = value

        return input
