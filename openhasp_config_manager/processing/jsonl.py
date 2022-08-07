import re
from typing import Dict

from openhasp_config_manager.model import Config


class JsonlObjectProcessor:
    PERCENTAGE_REGEX_PATTERN = re.compile(r"^\d+(\.\d+)?%$")

    def process(self, input: Dict, config: Config) -> Dict:
        result: Dict[str, any] = {}
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

                result[key] = self._percentage_of(numeric_value, total)
            else:
                result[key] = value

        # normalize value types, in case of templates
        for key, value in result.items():
            if key in [
                "page", "id",
                "x", "y", "w", "h",
                "text_font", "value_font",
                "radius", "border_side",
                "min", "max",
                "prev", "next",
            ] and isinstance(value, str):
                result[key] = int(float(value))

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
