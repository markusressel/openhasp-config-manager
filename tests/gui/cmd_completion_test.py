from openhasp_config_manager.gui.domain.source.cmd_completion import (
    cmd_help,
    cmd_insertion,
    cmd_words,
    continues,
    jsonl_object,
    jsonl_object_type,
    object_types,
)
from openhasp_config_manager.gui.domain.source.completion import CompletionContext, completion_context
from openhasp_config_manager.gui.domain.source.links import run_targets
from openhasp_config_manager.gui.domain.source.syntax import Language
from tests import TestBase
from tests.helpers import copy_test_config, load_session, write_page


def _context(line: str):
    return completion_context(line, Language.CMD)


class TestContext(TestBase):
    def test_command_at_the_start_of_a_line(self):
        assert _context("back") == CompletionContext("command", "back", 0)
        assert _context("  config/g") == CompletionContext("command", "config/g", 2)
        assert _context("") == CompletionContext("command", "", 0)

    def test_argument_of_a_command(self):
        assert _context("idle sh") == CompletionContext("argument", "sh", 5, key="idle")
        assert _context("backlight=o") == CompletionContext("argument", "o", 10, key="backlight")
        # takes anything, nothing to offer
        assert _context("json [") is None
        assert _context("unknown x") is None

    def test_second_argument_of_a_command(self):
        assert _context("service st") == CompletionContext("argument", "st", 8, key="service")
        assert _context("service start te") == CompletionContext("argument", "te", 14, key="service", target="start")
        assert _context("idle off x") is None

    def test_file_of_a_run(self):
        assert _context("run L:/pa") == CompletionContext("file", "L:/pa", 4)
        assert _context("run ") == CompletionContext("file", "", 4)

    def test_property_and_value_of_an_object(self):
        assert _context("p1b2.te") == CompletionContext("member", "te", 5, target="p1b2")
        assert _context("p12b30.align=ce") == CompletionContext("member_value", "ce", 13, key="align", target="p12b30")
        assert _context("p1b2.align ") == CompletionContext("member_value", "", 11, key="align", target="p1b2")

    def test_template_variable_comes_first(self):
        assert _context("page {{ pa") == CompletionContext("variable", "pa", 8)

    def test_object_of_a_jsonl_command_like_in_a_jsonl_file(self):
        assert _context('jsonl {"page": 1, "te') == CompletionContext("property", "te", 19)
        assert _context('jsonl {"align": "ce') == CompletionContext("value", "ce", 16, key="align")
        # the plate can't include files
        assert _context('jsonl {"!include": "co') is None

    def test_object_of_a_jsonl_command(self):
        found = jsonl_object('jsonl {"obj": "btn", "text": "a"}')
        assert [prop.key for prop in found.properties] == ["obj", "text"]
        assert jsonl_object("page 1") is None


class TestWords(TestBase):
    def test_commands(self):
        assert cmd_words(CompletionContext("command", "cl", 0)) == ["clearpage"]
        assert "config/mdns" in cmd_words(CompletionContext("command", "con", 0))

    def test_arguments(self):
        assert cmd_words(CompletionContext("argument", "", 5, key="page")) == ["next", "prev", "back"]
        assert cmd_words(CompletionContext("argument", "O", 5, key="idle")) == ["off"]
        assert cmd_words(CompletionContext("argument", "", 14, key="service", target="stop")) == ["http", "telnet", "console"]

    def test_files(self):
        context = CompletionContext("file", "L:/b", 4)
        assert cmd_words(context, lambda: ["boot.cmd", "pages.jsonl", "boot.cmd"]) == ["L:/boot.cmd"]

    def test_properties_and_methods_of_an_object(self):
        words = cmd_words(CompletionContext("member", "t", 5))
        assert "text" in words and "to_front" in words and "to_back" in words
        assert cmd_words(CompletionContext("member_value", "", 11, key="align")) == ["left", "center", "right", "auto"]

    def test_the_type_of_the_object_chooses_the_words(self):
        member = CompletionContext("member", "", 5, target="p1b2")
        assert "open" in cmd_words(member, object_type="dropdown")
        assert "open" not in cmd_words(member, object_type="btn")
        assert "min" in cmd_words(member, object_type="slider")
        assert "min" not in cmd_words(member, object_type="label")
        mode = CompletionContext("member_value", "", 10, key="mode", target="p1b2")
        assert cmd_words(mode) == []
        assert "dots" in cmd_words(mode, object_type="label")


class TestInsertion(TestBase):
    def test_command_with_an_argument_gets_a_space(self):
        context = CompletionContext("command", "ru", 0)
        assert cmd_insertion("ru", 2, context, "run").text == "run "
        assert continues(context, "run")
        assert cmd_insertion("reb", 3, CompletionContext("command", "reb", 0), "reboot").text == "reboot"
        # the rest of the word goes, the argument stays
        insertion = cmd_insertion("idx off", 2, CompletionContext("command", "id", 0), "idle")
        assert (insertion.start, insertion.end, insertion.text) == (0, 3, "idle")

    def test_property_gets_an_equals_sign(self):
        context = CompletionContext("member", "al", 5)
        assert cmd_insertion("p1b2.al", 7, context, "align").text == "align="
        assert continues(context, "align")
        assert cmd_insertion("p1b2.cl", 7, context, "clear").text == "clear"
        assert cmd_insertion("p1b2.al=left", 7, context, "align").text == "align"

    def test_argument_with_a_second_one_gets_a_space(self):
        context = CompletionContext("argument", "st", 8, key="service")
        assert cmd_insertion("service st", 10, context, "stop").text == "stop "
        assert continues(context, "stop")
        assert cmd_insertion("idle o", 6, CompletionContext("argument", "o", 5, key="idle"), "off").text == "off"

    def test_property_of_a_type_with_values_continues(self):
        context = CompletionContext("member", "mo", 5, target="p1b2")
        assert continues(context, "mode", "label")
        assert not continues(context, "mode")
        assert cmd_insertion("p1b2.op", 7, context, "open", "dropdown").text == "open"

    def test_file_replaces_the_typed_name(self):
        line = "run L:/pa.jsonl"
        insertion = cmd_insertion(line, 9, CompletionContext("file", "L:/pa", 4), "L:/pages.jsonl")
        assert line[: insertion.start] + insertion.text + line[insertion.end :] == "run L:/pages.jsonl"


class TestHelp(TestBase):
    def test_help_of_the_words(self):
        assert cmd_help(CompletionContext("command", "", 0), "idle").kind == "Command"
        assert cmd_help(CompletionContext("argument", "", 5, key="page"), "back").summary == "the page shown before"
        assert cmd_help(CompletionContext("member", "", 5), "delete").kind == "Method of an object"
        assert cmd_help(CompletionContext("member", "", 5), "text") is not None
        assert cmd_help(CompletionContext("member", "", 5), "open").kind == "Method of a `dropdown`"
        assert cmd_help(CompletionContext("member_value", "", 10, key="mode"), "dots", "label").summary


class TestObjectTypes(TestBase):
    def test_types_of_the_objects_of_a_device(self, tmp_path):
        root = copy_test_config(tmp_path)
        write_page(
            root, '{"page": 1, "id": 2, "obj": "slider"}\n{"id": 3, "obj": "dropdown"}\n{"page": 2, "id": 1, "obj": "btn"}\n'
        )
        session = load_session(root)
        types = object_types(session.working_objects.values())
        assert types["p1b2"] == "slider"
        # the page of the object before
        assert types["p1b3"] == "dropdown"
        assert types["p2b1"] == "btn"

    def test_type_of_the_object_of_a_jsonl_command(self):
        types = {"p1b2": "slider"}
        assert jsonl_object_type(jsonl_object('jsonl {"obj": "btn", "page": 1, "id": 2}'), types) == "btn"
        assert jsonl_object_type(jsonl_object('jsonl {"page": 1, "id": 2, "val": 3}'), types) == "slider"
        assert jsonl_object_type(jsonl_object('jsonl {"page": 1, "id": 9}'), types) is None


class TestRunTargets(TestBase):
    def test_a_device_sees_the_common_files_and_its_own(self, tmp_path):
        root = copy_test_config(
            tmp_path,
            {
                "common/page/md/content.jsonl": "",
                "devices/test_device/pages/home.jsonl": "",
                "devices/other/own.jsonl": "",
            },
        )
        names = run_targets(root, root / "devices/test_device/boot.cmd")
        assert "common_page_md_content.jsonl" in names
        assert "pages_home.jsonl" in names
        assert "own.jsonl" not in names
        assert "own.jsonl" in run_targets(root, root / "common/online.cmd")
