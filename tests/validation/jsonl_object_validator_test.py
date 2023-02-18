from openhasp_config_manager.validation.jsonl import JsonlObjectValidator
from tests import TestBase


class TestJsonlObjectValidator(TestBase):

    def test_something(self):
        # GIVEN
        under_test = JsonlObjectValidator()

        data = ""

        # WHEN
        result = under_test.validate(data=data)

        # THEN
        assert result
