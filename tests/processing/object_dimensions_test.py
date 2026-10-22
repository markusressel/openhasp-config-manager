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
