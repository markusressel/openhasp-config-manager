from openhasp_config_manager.openhasp_client.model.component import Component
from openhasp_config_manager.openhasp_client.model.configuration.config import Config
from openhasp_config_manager.validation.cmd import CmdFileValidator
from openhasp_config_manager.validation.jsonl import JsonlObjectValidator


class DeviceValidator:
    """
    A device specific validator, used to validate the result of the DeviceProcessor.
    """

    def __init__(self, config: Config, jsonl_object_validator: JsonlObjectValidator,
                 cmd_file_validator: CmdFileValidator):
        self._config = config
        self._jsonl_object_validator = jsonl_object_validator
        self._cmd_file_validator = cmd_file_validator

    def validate(self, component: Component, data: str):
        if component.type == "jsonl":
            self._jsonl_object_validator.validate(data)
        if component.type == "cmd":
            self._cmd_file_validator.validate(data)
        if len(component.name) > 30:
            raise AssertionError(
                f"Output file name length must not exceed 30 characters, but was {len(component.name)}: {component.name}")
