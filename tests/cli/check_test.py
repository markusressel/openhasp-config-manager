import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from openhasp_config_manager.check import check_config
from openhasp_config_manager.cli import cli
from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.gui.domain.problems import Severity

DEVICE = "devices/test_device"


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    return root


def _write(cfg_root: Path, content: str, name: str = "editor.jsonl"):
    (cfg_root / DEVICE / name).write_text(content)
    (cfg_root / DEVICE / "boot.cmd").write_text(f"run L:/{name}\n")


def _check(cfg_root: Path, device=None, hints=False):
    """:param hints: whether to keep the hints (the test config has variables nothing uses)"""
    devices, issues = check_config(_create_config_manager(cfg_root, cfg_root.parent / "output"), device)
    return devices, [issue for issue in issues if hints or issue.severity != Severity.HINT]


class TestCheck:
    def test_a_clean_config_has_no_issues(self, cfg_root):
        # WHEN
        devices, issues = _check(cfg_root)

        # THEN
        assert devices == ["test_device"]
        assert issues == []

    def test_nothing_is_written_to_the_output_directory(self, cfg_root):
        # WHEN
        _check(cfg_root)

        # THEN
        assert not (cfg_root.parent / "output").exists()

    def test_problems_of_the_pages_have_file_and_line(self, cfg_root):
        # GIVEN
        _write(cfg_root, '{"page": 9, "id": 1, "obj": "label"}\n{"page": 9, "id": 2, "obj": "btn", "x": 470, "y": 0}\n')

        # WHEN
        _, issues = _check(cfg_root)

        # THEN
        [issue] = issues
        assert issue.severity == Severity.WARNING
        assert issue.message == "p9b2 is outside of the screen: right by 70 px"
        assert (issue.device, issue.file, issue.line, issue.object) == ("test_device", f"{DEVICE}/editor.jsonl", 2, "p9b2")

    def test_unknown_template_variables_are_warnings(self, cfg_root):
        # GIVEN
        _write(cfg_root, '{"page": 9, "id": 1, "obj": "label", "text": "{{ no_such_variable }}"}\n')

        # WHEN
        _, issues = _check(cfg_root)

        # THEN
        [issue] = issues
        assert issue.severity == Severity.WARNING
        assert issue.message == "p9b1: text: Unknown variable: 'no_such_variable' is undefined"
        assert issue.line == 1

    def test_nested_templates_are_not_unknown_variables(self, cfg_root):
        # GIVEN
        _write(
            cfg_root,
            '{"page": 9, "id": 1, "obj": "label", "x": 5}\n'
            '{"page": 9, "id": 2, "obj": "label", "x": "{{ (p{{ 9 }}b1.x | int) + 5 }}"}\n',
        )

        # WHEN
        _, issues = _check(cfg_root)

        # THEN
        assert issues == []

    def test_what_a_deployment_fails_on_is_an_error_with_the_file(self, cfg_root):
        # GIVEN
        _write(cfg_root, '{"page": 9, "id": 1, "obj": "label"}\n{"page": 9, "id": 1, "obj": "btn"}\n')

        # WHEN
        _, issues = _check(cfg_root)

        # THEN
        errors = [issue for issue in issues if issue.severity == Severity.ERROR]
        assert any(issue.message.startswith("Validation failed: Duplicate id") and issue.file for issue in errors)
        assert any(issue.message == "p9b1: the id is used by 2 objects" and issue.line == 1 for issue in errors)
        assert issues[0].severity == Severity.ERROR

    def test_a_file_that_can_not_be_parsed_is_an_error_and_the_rest_is_still_checked(self, cfg_root):
        # GIVEN
        _write(cfg_root, '{"page": 9, "id": 1, "obj": "label", "x": 470}\n{"page": 9, "id": }\n')

        # WHEN
        _, issues = _check(cfg_root)

        # THEN
        assert any(issue.severity == Severity.ERROR and issue.file == f"{DEVICE}/editor.jsonl" for issue in issues)

    def test_an_unclosed_object_is_an_error(self, cfg_root):
        # GIVEN
        _write(cfg_root, '{"page": 9, "id": 1, "obj": "label"}\n{"page": 9, "id": 2,\n')

        # WHEN
        _, issues = _check(cfg_root)

        # THEN
        assert any(issue.severity == Severity.ERROR and "not closed" in issue.message for issue in issues)

    def test_an_unknown_device_is_an_error(self, cfg_root):
        # WHEN
        devices, issues = _check(cfg_root, "nope")

        # THEN
        assert devices == []
        assert [issue.message for issue in issues] == ["No device matches the filter: nope"]


class TestUnusedVariables:
    def _unused_file(self, cfg_root):
        _write(cfg_root, '{"page": 9, "id": 1, "obj": "label", "text": "{{ used }}"}\n')
        (cfg_root / DEVICE / "vars.yaml").write_text("used: 1\nunused: 2\n")

    def test_variables_no_device_uses_are_hints_with_file_and_line(self, cfg_root):
        # GIVEN
        self._unused_file(cfg_root)

        # WHEN
        _, issues = _check(cfg_root, hints=True)

        # THEN
        [issue] = [issue for issue in issues if issue.file.endswith("devices/test_device/vars.yaml") and issue.line == 2]
        assert issue.severity == Severity.HINT
        assert issue.message == "Not used: no file of any device uses unused"
        assert (issue.file, issue.line, issue.device) == (f"{DEVICE}/vars.yaml", 2, None)

    def test_they_are_not_reported_when_only_one_device_is_checked(self, cfg_root):
        # GIVEN
        self._unused_file(cfg_root)

        # WHEN
        _, issues = _check(cfg_root, "test_device", hints=True)

        # THEN: other devices might use them
        assert issues == []

    def test_hints_are_counted_apart_and_do_not_fail_the_check(self, cfg_root):
        # GIVEN
        self._unused_file(cfg_root)

        # WHEN
        result = CliRunner().invoke(cli, ["check", "-c", str(cfg_root)])

        # THEN
        assert result.exit_code == 0
        assert f"{DEVICE}/vars.yaml:2: hint: Not used" in result.stdout
        assert "Checked 1 device: 0 errors, 0 warnings, " in result.stdout and " hints" in result.stdout


class TestCheckCommand:
    def test_json_output_is_clean_and_the_exit_code_tells_about_errors(self, cfg_root):
        # GIVEN
        _write(cfg_root, '{"page": 9, "id": 1, "obj": "label"}\n{"page": 9, "id": 1, "obj": "btn"}\n')

        # WHEN
        result = CliRunner().invoke(cli, ["check", "-c", str(cfg_root), "--json"])

        # THEN
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["devices"] == ["test_device"]
        assert {issue["severity"] for issue in data["issues"]} == {"error", "hint"}

    def test_warnings_do_not_fail(self, cfg_root):
        # GIVEN
        _write(cfg_root, '{"page": 9, "id": 1, "obj": "label", "x": 470}\n')

        # WHEN
        result = CliRunner().invoke(cli, ["check", "-c", str(cfg_root)])

        # THEN
        assert result.exit_code == 0
        assert (
            f"{DEVICE}/editor.jsonl:1: warning: p9b1 is outside of the screen: right by 70 px [test_device]" in result.stdout
        )
        assert "Checked 1 device: 0 errors, 1 warning" in result.stdout
