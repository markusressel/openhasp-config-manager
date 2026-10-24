import json
import shutil
from pathlib import Path

import pytest

from openhasp_config_manager.cli.common import _create_config_manager
from openhasp_config_manager.gui.domain.connection import ConnectionStatus
from openhasp_config_manager.gui.domain.draft_files import load_device
from openhasp_config_manager.gui.domain.gui_state import (
    README,
    STATE_DIR_NAME,
    GuiStateFile,
    describe_connection,
    describe_draft,
    describe_files,
    describe_object,
    describe_problems,
)
from openhasp_config_manager.gui.domain.plate_session import PlateSession
from openhasp_config_manager.gui.domain.problems import Problem, Severity
from tests import TestBase

JSONL = """// a comment

{"page": 9, "id": 1, "obj": "label", "text": "A", "x": 10}
{
  "page": 9,
  "id": 2,
  "obj": "btn"
}
"""


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    device = root / "devices" / "test_device"
    (device / "editor.jsonl").write_text(JSONL)
    (device / "boot.cmd").write_text("run L:/editor.jsonl\n")
    return root.resolve()


@pytest.fixture
def session(cfg_root) -> PlateSession:
    loaded = load_device(_create_config_manager(cfg_root, cfg_root.parent / "output"), "test_device")
    session = PlateSession(device=loaded.device)
    session.load(loaded.components, loaded.renderer)
    return session


class TestDescribe(TestBase):
    def test_object_has_its_file_and_line(self, session, cfg_root):
        # GIVEN
        [component] = session.components
        label, button = session.working_objects[component.key]

        # THEN
        assert describe_object(session, button, cfg_root) == {
            "name": "p9b2",
            "id": 2,
            "page": 9,
            "type": "btn",
            "file": "devices/test_device/editor.jsonl",
            "line": 4,
        }
        assert describe_object(session, label, cfg_root)["line"] == 3

    def test_object_added_in_the_draft_has_no_line(self, session, cfg_root):
        # GIVEN
        [component] = session.components
        added = session.add_object(component.key, {"page": 9, "id": 3, "obj": "btn"})

        # THEN
        assert describe_object(session, added, cfg_root)["line"] is None

    def test_problems_name_their_object_and_line(self, session, cfg_root):
        # GIVEN
        [component] = session.components
        button = session.working_objects[component.key][1]

        # WHEN
        result = describe_problems(session, [Problem(Severity.WARNING, button, "p9b2 is outside of the screen")], cfg_root)

        # THEN
        assert result == [
            {
                "severity": "warning",
                "message": "p9b2 is outside of the screen",
                "object": "p9b2",
                "file": "devices/test_device/editor.jsonl",
                "line": 4,
            }
        ]

    def test_draft_lists_changed_added_and_deleted_objects(self, session, cfg_root):
        # GIVEN
        [component] = session.components
        label, button = session.working_objects[component.key]
        assert describe_draft(session, cfg_root) == {"modified": False, "files": []}

        # WHEN
        session.set_source_value(label, "x", 20)
        session.add_object(component.key, {"page": 9, "id": 3, "obj": "btn"})
        session.remove_object(button)

        # THEN
        assert describe_draft(session, cfg_root) == {
            "modified": True,
            "files": [
                {
                    "file": "devices/test_device/editor.jsonl",
                    "changed": ["p9b1"],
                    "added": ["p9b3"],
                    "deleted": ["p9b2"],
                }
            ],
        }

    def test_files_have_their_pages(self, session, cfg_root):
        # THEN
        assert describe_files(session.components, session.working_objects, cfg_root) == [
            {"file": "devices/test_device/editor.jsonl", "shared": False, "pages": [9]}
        ]

    def test_connection(self):
        # WHEN
        status = ConnectionStatus.connecting().with_broker(False, "x" * 600).with_send_failed(3)

        # THEN
        result = describe_connection(status)
        assert result["state"] == "broker_unreachable"
        assert len(result["error"]) == 501
        assert result["out_of_sync_pages"] == [3]


class TestGuiStateFile(TestBase):
    def test_creates_the_folder_with_gitignore_and_readme(self, tmp_path):
        # WHEN
        GuiStateFile(tmp_path).write({"running": True, "updated": "a"})

        # THEN
        folder = tmp_path / STATE_DIR_NAME
        assert json.loads((folder / "gui-state.json").read_text()) == {"running": True, "updated": "a"}
        assert (folder / ".gitignore").read_text() == "*\n"
        assert (folder / "README.md").read_text() == README
        assert [path.name for path in folder.iterdir() if path.name.endswith(".tmp")] == []

    def test_nothing_is_written_if_only_the_time_changed(self, tmp_path):
        # GIVEN
        file = GuiStateFile(tmp_path)
        file.write({"running": True, "updated": "a"})

        # WHEN
        file.write({"running": True, "updated": "b"})

        # THEN
        assert json.loads(file.path.read_text())["updated"] == "a"

        # WHEN
        file.write({"running": False, "updated": "c"})

        # THEN
        assert json.loads(file.path.read_text()) == {"running": False, "updated": "c"}

    def test_a_config_directory_that_can_not_be_written_is_no_error(self, tmp_path):
        # GIVEN
        (tmp_path / STATE_DIR_NAME).write_text("a file where the folder should be")

        # WHEN / THEN
        GuiStateFile(tmp_path).write({"running": True})
