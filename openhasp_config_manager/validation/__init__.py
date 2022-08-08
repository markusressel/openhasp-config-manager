from openhasp_config_manager.model import Config, Component
from openhasp_config_manager.validation.jsonl import JsonlObjectValidator


class DeviceValidator:
    """
    A device specific validator, used to validate the result of the DeviceProcessor.
    """

    def __init__(self, config: Config, jsonl_object_validator: JsonlObjectValidator):
        self._config = config
        self._jsonl_object_validator = jsonl_object_validator

    def validate(self, component: Component, data: str):
        if component.type == "jsonl":
            self._jsonl_object_validator.validate(data)
        if component.type == "cmd":
            pass
            # self._cmd_file_validator.validate(component)
        if len(component.name) > 30:
            raise AssertionError(f"Output file name length must not exceed 30 characters: {component.name}")
