from openhasp_config_manager.processing import render_dict_recursively
from tests import TestBase


class TestUtils(TestBase):

    def test_render_dict_recursively(self):
        # GIVEN
        input_data = {
            "{{ key }}": "{{ value }}"
        }
        template_vars = {
            "key": "key_rendered",
            "value": "value_rendered"
        }

        # WHEN
        result = render_dict_recursively(
            input=input_data,
            template_vars=template_vars
        )

        # THEN
        assert result == {
            "key_rendered": "value_rendered"
        }
