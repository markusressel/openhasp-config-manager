import logging

import pytest

from openhasp_config_manager.processing.jsonl.jsonl import ObjectDimensionsProcessor, is_numeric_property
from tests import TestBase


def test_numeric_text_is_converted():
    result = ObjectDimensionsProcessor().process({"x": "12.7", "text": "a"}, config=None, template_vars={})

    assert result == {"x": 12, "text": "a"}


def test_text_that_is_not_a_number_logs_one_line(caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        result = ObjectDimensionsProcessor().process({"obj": "btn", "x": "left"}, config=None, template_vars={})

    assert result == {"obj": "btn", "x": "left"}
    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info is None
    assert capsys.readouterr().out == ""


def test_font_name_stays_a_name_without_a_warning(caplog):
    with caplog.at_level(logging.DEBUG):
        result = ObjectDimensionsProcessor().process(
            {"text_font": "fonts_roboto24", "value_font10": "arial_20", "text_font20": "24"}, config=None, template_vars={}
        )

    assert result == {"text_font": "fonts_roboto24", "value_font10": "arial_20", "text_font20": 24}
    assert caplog.records == []


@pytest.mark.parametrize(
    "key",
    ["page", "id", "x", "y", "w", "h", "min", "max", "prev", "next", "radius", "radius10", "radius21", "border_width"]
    + ["border_width12", "pad_top", "pad_inner", "pad_left10", "margin_top", "margin_bottom21"],
)
def test_numeric_properties(key):
    assert is_numeric_property(key)


@pytest.mark.parametrize(
    "key", ["hidden", "height", "width", "xy", "ids", "pages", "maximum", "radius100", "margin", "pad_", "text_font", "val"]
)
def test_properties_that_are_not_numbers_although_they_start_like_one(key):
    assert not is_numeric_property(key)


def test_rendered_values_of_properties_that_are_not_numbers_stay_text_without_a_warning(caplog):
    with caplog.at_level(logging.DEBUG):
        result = ObjectDimensionsProcessor().process(
            {"hidden": "true", "enabled": "0", "height": "50%", "text": "12"}, config=None, template_vars={}
        )

    assert result == {"hidden": "true", "enabled": "0", "height": "50%", "text": "12"}
    assert caplog.records == []


def test_style_variants_of_numeric_properties_are_numbers():
    result = ObjectDimensionsProcessor().process(
        {"radius10": "8", "border_width12": "2.0", "pad_top10": "4", "margin_left": "1"}, config=None, template_vars={}
    )

    assert result == {"radius10": 8, "border_width12": 2, "pad_top10": 4, "margin_left": 1}


class TestPercentages(TestBase):
    def test_percentages_of_the_screen(self):
        # the default config is 320 wide and 480 high
        result = ObjectDimensionsProcessor().process(
            {"x": "50%", "w": "25%", "y": "10%", "h": "12.5%", "radius": "50%"}, config=self.default_config, template_vars={}
        )

        assert result == {"x": 160, "w": 80, "y": 48, "h": 60, "radius": "50%"}
