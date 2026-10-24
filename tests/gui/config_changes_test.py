from pathlib import Path

from openhasp_config_manager.gui.domain.config_changes import OwnWrites, is_relevant_change
from tests import TestBase


class TestIsRelevantChange(TestBase):
    def test_config_files_are_relevant(self):
        for name in ["devices/a/boot.cmd", "common/x.jsonl", "devices/a/vars.yaml", "devices/a/home"]:
            assert is_relevant_change(Path("/cfg", name)) is True, name

    def test_temporary_files_of_editors_are_not_relevant(self):
        for name in ["a.jsonl~", "a.jsonl.swp", "4913", ".#a.jsonl", "#a.jsonl#", "a.jsonl.tmp", ".DS_Store"]:
            assert is_relevant_change(Path("/cfg/devices/a", name)) is False, name

    def test_version_control_and_tool_folders_are_not_relevant(self):
        for name in [".git/index", ".idea/workspace.xml", "x/__pycache__/a.pyc", ".venv/lib/a.py"]:
            assert is_relevant_change(Path("/cfg", name)) is False, name

    def test_ignored_roots_are_not_relevant(self):
        assert is_relevant_change(Path("/cfg/output/a/boot.cmd"), [Path("/cfg/output")]) is False
        assert is_relevant_change(Path("/cfg/outputs/a.cmd"), [Path("/cfg/output")]) is True


class TestOwnWrites(TestBase):
    def test_a_file_with_the_written_content_is_not_foreign(self, tmp_path):
        # GIVEN
        path = tmp_path / "a.jsonl"
        path.write_text("one")
        writes = OwnWrites()
        writes.written(path, "one")

        # THEN
        assert writes.foreign([path]) == set()

    def test_a_file_changed_after_the_write_is_foreign(self, tmp_path):
        # GIVEN
        path = tmp_path / "a.jsonl"
        path.write_text("one")
        writes = OwnWrites()
        writes.written(path, "one")

        # WHEN
        path.write_text("two")

        # THEN
        assert writes.foreign([path]) == {path}

    def test_a_deleted_file_is_foreign(self, tmp_path):
        # GIVEN
        path = tmp_path / "a.jsonl"
        writes = OwnWrites()
        writes.written(path, "one")

        # THEN
        assert writes.foreign([path]) == {path}

    def test_a_file_the_app_never_wrote_is_foreign(self, tmp_path):
        # GIVEN
        path = tmp_path / "a.jsonl"
        path.write_text("one")

        # THEN
        assert OwnWrites().foreign([path]) == {path}
