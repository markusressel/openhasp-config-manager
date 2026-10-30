import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from openhasp_config_manager.check import check_config, check_device_files
from openhasp_config_manager.cli import cli
from openhasp_config_manager.gui.domain.problems import Severity
from tests.helpers import DEVICE_DIR, TEST_DEVICE, copy_test_config, create_config_manager, write_page

# a page in the common folder whose variable needs `pages.room`, run by a .cmd file that no startup script runs
ROOM_PAGE = {
    "common/room/vars.yaml": 'title: "Room"\npage_index: "{{ pages.room.index }}"\n',
    "common/room/content.jsonl": '{"page": "{{ page_index }}", "id": 1, "obj": "label"}\n',
    "common/room/header.jsonl": '{"page": "{{ page_index }}", "id": 2, "obj": "label"}\n',
    "common/room/page.cmd": "run L:/common_room_content.jsonl\nrun L:/common_room_header.jsonl\n",
}


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    root = copy_test_config(tmp_path, ROOM_PAGE)
    write_page(root, '{"page": 9, "id": 1, "obj": "label"}\n')
    return root


def _errors(cfg_root: Path, device=None):
    _, issues = check_config(create_config_manager(cfg_root), device)
    return [issue for issue in issues if issue.severity == Severity.ERROR]


def _add_device(cfg_root: Path, name: str, variables: str):
    shutil.copytree(cfg_root / DEVICE_DIR, cfg_root / "devices" / name)
    (cfg_root / "devices" / name / "vars.yaml").write_text(variables)


class TestUnknownVariableInAVariable:
    def test_is_reported_once_at_the_variable_with_the_files_that_need_it(self, cfg_root):
        # WHEN
        [error] = _errors(cfg_root)

        # THEN
        assert (error.file, error.line, error.device) == ("common/room/vars.yaml", 2, TEST_DEVICE)
        assert error.message == (
            "Unknown variable 'pages' in the variable 'page_index': {{ pages.room.index }} "
            "(needed by common/room/content.jsonl, common/room/header.jsonl)"
        )

    def test_names_the_devices_that_have_it(self, cfg_root):
        # GIVEN
        _add_device(cfg_root, "other_device", "pages:\n  room:\n    index: 3\n")

        # WHEN: also when only the device without it is checked
        [error] = _errors(cfg_root, TEST_DEVICE)

        # THEN
        assert error.hints[0] == (
            "'pages' is defined for other_device (devices/other_device/vars.yaml:1), but not for test_device. Define it "
            "for test_device too, in a YAML file of the folder of test_device (devices/test_device), or for all devices "
            "in a YAML file of the common folder."
        )

    def test_suggests_names_it_may_be_a_typo_of(self, cfg_root):
        # GIVEN
        (cfg_root / DEVICE_DIR / "vars.yaml").write_text("pages:\n  rooms:\n    index: 3\n")

        # WHEN
        [error] = _errors(cfg_root)

        # THEN
        assert error.message.startswith("Unknown variable 'pages.room' in the variable 'page_index'")
        assert error.hints[0] == "No YAML file defines 'pages.room'. Did you mean 'pages.rooms'?"

    def test_says_when_nothing_defines_it(self, cfg_root):
        # WHEN
        [error] = _errors(cfg_root)

        # THEN
        assert error.hints[0] == "No YAML file defines 'pages': add it to a YAML file, or remove it from 'page_index'."


class TestFilesNoStartupScriptRuns:
    def test_get_a_hint_that_the_device_may_not_need_them(self, cfg_root):
        # WHEN
        [error] = _errors(cfg_root)

        # THEN
        assert error.hints[-1] == (
            "No startup script of test_device runs common/room/page.cmd, but it is deployed with the files it runs (every "
            ".cmd file is). If test_device doesn't need them, delete them, or move them into the folders of the devices "
            "that use them."
        )

    def test_used_files_get_no_such_hint(self, cfg_root):
        # GIVEN
        (cfg_root / DEVICE_DIR / "boot.cmd").write_text("run L:/editor.jsonl\nrun L:/common_room_page.cmd\n")

        # WHEN
        [error] = _errors(cfg_root)

        # THEN
        assert not any("startup script" in hint for hint in error.hints)


class TestOtherErrors:
    def test_a_cycle_is_reported_at_the_variable(self, cfg_root):
        # GIVEN
        (cfg_root / "common/room/vars.yaml").write_text('page_index: 1\na: "{{ b }}"\nb: "{{ a }}"\n')

        # WHEN
        [error] = _errors(cfg_root)

        # THEN
        assert error.file == "common/room/vars.yaml"
        assert error.line in (2, 3)
        assert "cycle" in error.message

    def test_an_error_of_a_file_is_reported_at_the_file(self, cfg_root):
        # GIVEN
        write_page(cfg_root, '{"page": 9, "id": }\n')
        (cfg_root / DEVICE_DIR / "vars.yaml").write_text("pages:\n  room:\n    index: 3\n")

        # WHEN
        [error] = _errors(cfg_root)

        # THEN
        assert (error.file, error.line) == (f"{DEVICE_DIR}/editor.jsonl", None)
        assert error.message.startswith("Can't process the file:")


class TestCheckDeviceFiles:
    def test_has_the_errors_a_deployment_fails_on(self, cfg_root):
        # WHEN
        [error] = check_device_files(create_config_manager(cfg_root), TEST_DEVICE)

        # THEN
        assert error.file == "common/room/vars.yaml"
        assert error.hints

    def test_an_unknown_device_is_an_error(self, cfg_root):
        with pytest.raises(ValueError, match="nope is not in the config directory anymore"):
            check_device_files(create_config_manager(cfg_root), "nope")


class TestCommand:
    def test_prints_the_hints_below_the_error(self, cfg_root):
        # WHEN
        result = CliRunner().invoke(cli, ["check", "-c", str(cfg_root)])

        # THEN
        lines = result.stdout.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("common/room/vars.yaml:2: error:"))
        assert (
            lines[index + 1] == "  hint: No YAML file defines 'pages': add it to a YAML file, or remove it from 'page_index'."
        )
        assert lines[index + 2].startswith("  hint: No startup script of test_device runs common/room/page.cmd")
