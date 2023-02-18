from pathlib import Path

from openhasp_config_manager.model import Component
from openhasp_config_manager.validation.cmd import CmdFileValidator
from openhasp_config_manager.validation.device_validator import DeviceValidator
from openhasp_config_manager.validation.jsonl import JsonlObjectValidator
from tests import TestBase


class TestDeviceValidator(TestBase):

    def test_example_config(self):
        # GIVEN
        device_validator = DeviceValidator(
            config=self.default_config,
            # TODO: mock validators
            jsonl_object_validator=JsonlObjectValidator(),
            cmd_file_validator=CmdFileValidator()
        )

        component = Component(
            name="name",
            type="",
            path=Path(),
            content="",
        )
        data = ""

        # WHEN
        device_validator.validate(
            component=component,
            data=data
        )

        # THEN
        assert True
