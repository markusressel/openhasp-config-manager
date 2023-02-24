from openhasp_config_manager.processing import render_dict_recursive
from tests import TestBase


class TestUtils(TestBase):

    def test_render_dict_recursively__template_rendering_works(self):
        # GIVEN
        input_data = {
            "{{ key }}": "{{ value }}"
        }
        template_vars = {
            "key": "key_rendered",
            "value": "value_rendered"
        }

        # WHEN
        result = render_dict_recursive(
            input=input_data,
            template_vars=template_vars
        )

        # THEN
        assert result == {
            "key_rendered": "value_rendered"
        }

    def test_render_dict_recursively__two_step_rendering(self):
        # GIVEN
        input_data = {
            "A": "B",
            "B": "{{ A }}",
            "C": "{{ B }}",
        }

        template_vars = {}

        # WHEN
        result = render_dict_recursive(
            input=input_data,
            template_vars=template_vars
        )

        # THEN
        assert result == {
            'A': 'B',
            'B': 'B',
            'C': 'B'
        }

    def test_render_dict_recursively__inner_template(self):
        # GIVEN
        input_data = {
            "A": "{{ {{ B }}{{ C }}",
            "B": "1",
            "C": "2",
        }

        template_vars = {}

        # WHEN
        result = render_dict_recursive(
            input=input_data,
            template_vars=template_vars
        )

        # THEN
        assert result == {
            'A': '12',
            "B": "1",
            "C": "2",
        }
