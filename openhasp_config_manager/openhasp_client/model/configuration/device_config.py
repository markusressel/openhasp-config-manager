from dataclasses import dataclass

from openhasp_config_manager.const import MAX_FILE_NAME_LENGTH_KEY, PLATE_FILE_NAME_MAX
from openhasp_config_manager.openhasp_client.model.configuration.screen_config import ScreenConfig


@dataclass
class DeviceConfig:
    ip: str
    screen: ScreenConfig
    # the longest file name the plate accepts (the flattened path), lower than the default on e.g. an ESP8266
    max_file_name_length: int = PLATE_FILE_NAME_MAX


def max_file_name_length(section: dict) -> int:
    """
    :param section: the `openhasp_config_manager` section of a device's config.json
    :return: the longest file name the plate accepts: `device.max_file_name_length`, `PLATE_FILE_NAME_MAX` if it isn't set
    :raises ValueError: if it is set to something else than a positive whole number
    """
    value = section.get("device", {}).get(MAX_FILE_NAME_LENGTH_KEY, PLATE_FILE_NAME_MAX)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"openhasp_config_manager.device.{MAX_FILE_NAME_LENGTH_KEY} must be a positive whole number, not {value!r}"
        )
    return value
