import logging

from openhasp_config_manager.processing.jsonl.jsonl import ObjectDimensionsProcessor


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
