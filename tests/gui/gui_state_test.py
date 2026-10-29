import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from openhasp_config_manager.gui.domain.connection import ConnectionStatus
from openhasp_config_manager.gui.domain.draft.files import load_device
from openhasp_config_manager.gui.domain.gui_state import (
    README,
    STATE_DIR_NAME,
    GuiStateFile,
    describe_connection,
    describe_device,
    EditorTab,
    describe_draft,
    describe_editor,
    describe_files,
    describe_object,
    describe_part_mode,
    describe_problems,
)
from openhasp_config_manager.gui.domain.draft.part_focus import PartFocus
from openhasp_config_manager.gui.domain.draft.session import PlateSession
from openhasp_config_manager.gui.domain.problems import Problem, Severity
from tests import TestBase
from tests.helpers import copy_test_config, create_config_manager, load_session, write_page

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
    root = copy_test_config(tmp_path)
    write_page(root, JSONL)
    return root.resolve()


@pytest.fixture
def session(cfg_root) -> PlateSession:
    return load_session(cfg_root)


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
            "rendered": {},
            "source": {},
        }
        assert describe_object(session, label, cfg_root)["line"] == 3

    def test_an_included_object_says_where_it_is_written(self, cfg_root):
        # GIVEN
        (cfg_root / "common" / "dot.jsonl").write_text('{"page": 9, "id": "{{ id }}", "obj": "obj", "x": "{{ id }}"}\n')
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(
            '{"!include": "common/dot.jsonl", "vars": {"size": "{{ range(2) }}"}, "for": {"id": [4]}}\n'
        )
        loaded = load_device(create_config_manager(cfg_root), "test_device")
        session = PlateSession(device=loaded.device)
        session.load(loaded.components, loaded.renderer)
        [component] = session.components
        [dot] = session.working_objects[component.key]

        # WHEN
        location = describe_object(session, dot, cfg_root)
        [problem] = describe_problems(session, [Problem(Severity.WARNING, dot, "a problem")], cfg_root)

        # THEN: what JSON can't hold is text
        assert (location["file"], location["line"], location["source"]) == (
            "devices/test_device/editor.jsonl",
            1,
            {"x": "{{ id }}"},
        )
        assert location["include"] == {
            "file": "common/dot.jsonl",
            "line": 1,
            "chain": [
                {"file": "devices/test_device/editor.jsonl", "line": 1, "vars": {"size": "range(0, 2)"}, "loop": {"id": 4}}
            ],
        }
        assert problem["include"] == location["include"]
        json.dumps(location)

    def test_part_mode_names_the_part_and_the_instance(self, cfg_root):
        # GIVEN
        (cfg_root / "common" / "dot.jsonl").write_text('{"page": 9, "id": "{{ id }}", "obj": "obj"}\n')
        (cfg_root / "devices" / "test_device" / "editor.jsonl").write_text(
            '{"!include": "common/dot.jsonl", "for": {"id": [4, 5]}}\n'
        )
        loaded = load_device(create_config_manager(cfg_root), "test_device")
        session = PlateSession(device=loaded.device)
        session.load(loaded.components, loaded.renderer)
        assert describe_part_mode(None, cfg_root) is None

        # WHEN
        instance = session.part_instances(cfg_root / "common" / "dot.jsonl")[1]
        focus = PartFocus(session, instance)

        # THEN
        assert describe_part_mode(focus, cfg_root) == {
            "part": "common/dot.jsonl",
            "instance": session.describe_instance(instance),
            "shared": True,
            "alone": False,
        }
        assert "id=5" in session.describe_instance(instance)

        # WHEN: its objects are all removed
        [dot] = focus.objects()
        focus.remove_object(dot)

        # THEN
        assert describe_part_mode(focus, cfg_root)["instance"] is None

    def test_object_has_rendered_and_written_geometry(self, session, cfg_root):
        # GIVEN
        [component] = session.components
        label = session.working_objects[component.key][0]
        added = session.add_object(component.key, {"page": 9, "id": 3, "obj": "btn", "x": 1, "w": "{{ 2 * 5 }}"})

        # THEN
        assert describe_object(session, label, cfg_root)["rendered"] == {"x": 10}
        location = describe_object(session, added, cfg_root)
        assert location["rendered"] == {"x": 1, "w": 10}
        assert location["source"] == {"x": 1, "w": "{{ 2 * 5 }}"}

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
        [component] = session.components
        devices = [
            SimpleNamespace(name="b", jsonl=[SimpleNamespace(path=component.path)]),
            SimpleNamespace(name="a", jsonl=[SimpleNamespace(path=component.path)]),
            SimpleNamespace(name="c", jsonl=[SimpleNamespace(path=component.path.parent / "other.jsonl")]),
        ]
        result = describe_problems(
            session, [Problem(Severity.WARNING, button, "p9b2 is outside of the screen")], cfg_root, devices
        )

        # THEN
        assert result == [
            {
                "severity": "warning",
                "message": "p9b2 is outside of the screen",
                "object": "p9b2",
                "file": "devices/test_device/editor.jsonl",
                "line": 4,
                "rendered": {},
                "source": {},
                "devices": ["a", "b"],
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

    def test_device_describes_what_the_editor_shows(self, session, cfg_root):
        # GIVEN
        [component] = session.components
        label, button = session.working_objects[component.key]
        session.set_source_value(label, "x", 20)

        # WHEN
        result = describe_device(
            session,
            session.device,
            cmd="boot.cmd",
            page=9,
            edit_mode=True,
            live_preview=False,
            selection=[button],
            target_component=component.key,
            config_dir=cfg_root,
        )

        # THEN
        assert result == {
            "name": "test_device",
            "folder": "devices/test_device",
            "cmd": "boot.cmd",
            "screen": {"width": 480, "height": 320},
            "files": describe_files(session.components, session.working_objects, cfg_root),
            "page": 9,
            "pages": [9],
            "edit_mode": True,
            "live_preview": False,
            "selection": [describe_object(session, button, cfg_root)],
            "new_objects_file": "devices/test_device/editor.jsonl",
            "part_mode": None,
            "draft": describe_draft(session, cfg_root),
            "loaded": session.loaded_at.isoformat(timespec="milliseconds"),
        }
        assert result["draft"]["modified"]
        json.dumps(result)

    def test_device_without_a_file_for_new_objects(self, session, cfg_root):
        # WHEN
        result = describe_device(
            session,
            session.device,
            cmd="boot.cmd",
            page=9,
            edit_mode=False,
            live_preview=True,
            selection=[],
            target_component=None,
            config_dir=cfg_root,
        )

        # THEN
        assert (result["new_objects_file"], result["selection"], result["live_preview"]) == (None, [], True)

    def test_device_in_part_mode_puts_new_objects_into_the_part(self, cfg_root):
        # GIVEN
        part = cfg_root / "common" / "dot.jsonl"
        part.write_text('{"page": 9, "id": "{{ id }}", "obj": "obj"}\n')
        write_page(cfg_root, '{"!include": "common/dot.jsonl", "for": {"id": [4]}}\n')
        session = load_session(cfg_root)
        [instance] = session.part_instances(part)
        focus = PartFocus(session, instance)

        # WHEN
        result = describe_device(
            session,
            session.device,
            cmd="boot.cmd",
            page=9,
            edit_mode=True,
            live_preview=False,
            selection=[],
            target_component=str(part),
            config_dir=cfg_root,
            part_focus=focus,
        )

        # THEN
        assert result["new_objects_file"] == "common/dot.jsonl"
        assert result["part_mode"] == describe_part_mode(focus, cfg_root)

    def test_files_have_their_pages(self, session, cfg_root):
        # THEN
        assert describe_files(session.components, session.working_objects, cfg_root) == [
            {"file": "devices/test_device/editor.jsonl", "shared": False, "pages": [9]}
        ]

    def test_editor_tabs(self, cfg_root):
        tabs = [
            EditorTab(cfg_root / "a.jsonl", dirty=True, conflict=False, line=3, column=7),
            EditorTab(cfg_root / "devices" / "b.yaml", dirty=False, conflict=True, line=1, column=1),
        ]

        assert describe_editor("split", tabs, cfg_root / "a.jsonl", cfg_root) == {
            "mode": "split",
            "current": "a.jsonl",
            "files": [
                {"file": "a.jsonl", "dirty": True, "conflict": False, "line": 3, "column": 7},
                {"file": "devices/b.yaml", "dirty": False, "conflict": True, "line": 1, "column": 1},
            ],
        }
        assert describe_editor("rendered", [], None, cfg_root) == {"mode": "rendered", "current": None, "files": []}

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
        assert GuiStateFile(tmp_path).write_preview(b"png") is None

    def test_the_preview_is_written_when_it_changed_and_removed_without_a_page(self, tmp_path, monkeypatch):
        # GIVEN
        file = GuiStateFile(tmp_path)
        times = iter(["t1", "t2"])
        monkeypatch.setattr("openhasp_config_manager.gui.domain.gui_state.now", lambda: next(times))

        # WHEN
        first = file.write_preview(b"one")
        same = file.write_preview(b"one")

        # THEN
        assert first == same == {"file": ".openhasp-config-manager/preview.png", "updated": "t1"}
        assert file.preview_path.read_bytes() == b"one"
        assert (tmp_path / STATE_DIR_NAME / ".gitignore").exists()

        # WHEN
        changed = file.write_preview(b"two")

        # THEN
        assert changed["updated"] == "t2"
        assert file.preview_path.read_bytes() == b"two"

        # WHEN
        assert file.write_preview(None) is None

        # THEN
        assert not file.preview_path.exists()
