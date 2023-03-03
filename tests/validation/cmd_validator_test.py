import textwrap

from openhasp_config_manager.validation.cmd import CmdFileValidator
from tests import TestBase


class TestCmdFileValidator(TestBase):

    def test_single_jsonl_command_valid(self):
        # GIVEN
        under_test = CmdFileValidator()

        data = textwrap.dedent("""
            jsonl {"obj":"btn","id":14,"x":120,"y":1,"w":30,"h":40,"text_font":"2","text":"Test","text_color":"gray","bg_opa":0,"border_width":0}
        """).strip()

        # WHEN
        under_test.validate(data)

        # THEN
        assert True

    def test_single_jsonl_command_invalid(self):
        # GIVEN
        under_test = CmdFileValidator()

        data = textwrap.dedent("""
           jsonl {"obj":"btn","id":14,"x":120,"y":1,"w":30,"h":40,"text_font":"2","text":"Test","text_color":"gray","bg_opa":0,"border_width":0
        """).strip()

        try:
            # WHEN
            under_test.validate(data=data)
            assert False
        except Exception as ex:
            # THEN
            assert "jsonl command argument cannot be parsed" in str(ex)
