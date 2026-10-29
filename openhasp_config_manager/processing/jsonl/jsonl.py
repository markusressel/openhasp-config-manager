import logging
import re
from contextlib import suppress
from typing import Any, Dict, Optional

from openhasp_config_manager.openhasp_client.model.configuration.config import Config
from openhasp_config_manager.processing.jsonl import JsonlObjectProcessor

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)


# the properties whose values are converted to int (e.g. after rendering a template), as a regex alternation of whole names:
# `radius` and `border_width` with the digits of the part and the state of a style (`radius10`), `pad_*` and `margin_*` with them too
NUMERIC_PROPERTY_NAMES = r"page|id|x|y|w|h|radius\d{0,2}|pad_.+|margin_.+|border_width\d{0,2}|min|max|prev|next"
NUMERIC_PROPERTY = re.compile(f"(?:{NUMERIC_PROPERTY_NAMES})")
# the font properties (`text_font`, `value_font10`, ...): a number for a built-in font, or the name of a font file on the plate
FONT_PROPERTY = re.compile(r"^\w*_font\d*$")
# the properties that can be a percentage of the screen size
_PERCENTAGE_PROPERTIES = ("x", "y", "w", "h")


def is_numeric_property(key: str) -> bool:
    """:return: whether the value of a property is a number (see `NUMERIC_PROPERTY_NAMES`), e.g. `x` but not `hidden`"""
    return NUMERIC_PROPERTY.fullmatch(key) is not None


class ObjectDimensionsProcessor(JsonlObjectProcessor):
    """
    Used to process .jsonl files to add support for additional features.
    """

    PERCENTAGE_REGEX_PATTERN = re.compile(r"^\d+(\.\d+)?%$")

    def process(
        self,
        input: Dict,
        config: Config,
        template_vars: Dict[str, any],
    ) -> Dict:
        return {key: self.normalize_value(key, value, config, input) for key, value in input.items()}

    def normalize_value(self, key: str, value: Any, config: Config, obj: Optional[Dict] = None) -> Any:
        """
        :return: the value of a property the way it is sent to the plate: a percentage of the screen size in pixels, a number
            of a numeric property (e.g. after rendering a template) as int, other values as they are
        :param obj: the object of the property, to log a value that should be a number but isn't; None to not log it
        """
        if not isinstance(value, str):
            return value
        if key in _PERCENTAGE_PROPERTIES and self.PERCENTAGE_REGEX_PATTERN.match(value):
            screen = config.openhasp_config_manager.device.screen
            return self._percentage_of(self._parse_percentage(value), screen.width if key in ("x", "w") else screen.height)
        if FONT_PROPERTY.match(key):
            # a font name stays as it is
            with suppress(ValueError):
                return int(float(value))
            return value
        if is_numeric_property(key):
            try:
                return int(float(value))
            except ValueError as ex:
                if obj is not None:
                    LOGGER.warning(f"{key}: {value!r} is not a number ({ex}), object: {obj}")
        return value

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
        return float(str(value).replace("%", ""))


class ObjectThemeProcessor(JsonlObjectProcessor):
    """
    Used to apply default theming from "theme.obj.*" values
    """

    def process(
        self,
        input: Dict,
        config: Config,
        template_vars: Dict[str, any],
    ) -> Dict:
        obj_key = input.get("obj", None)
        if obj_key is None:
            return input

        theme_values = template_vars.get("theme", {}).get("obj", {}).get(obj_key, {})
        for key, value in theme_values.items():
            if key not in input:
                input[key] = value

        return input
