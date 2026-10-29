"""The file operations of the Files tree (Qt-free): what they change, and what they refuse."""

from pathlib import Path

import pytest

from openhasp_config_manager.gui.domain.file_operations import (
    ConfigFiles,
    FileOperationError,
    FileReference,
    apply_plan,
    move_targets,
    plan_create,
    plan_delete,
    plan_move,
)

PART = '{"page": "{{ page }}", "id": 1, "obj": "label"}\n'


def _write(root: Path, files: dict):
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content)


@pytest.fixture
def root(tmp_path) -> Path:
    root = tmp_path / "cfg"
    _write(
        root,
        {
            "theme.yaml": "theme: {}\n",
            "common/page/home.jsonl": '{"page": 1, "id": 1, "obj": "img", "src": "L:/common_page_empty.png"}\n'
            '{"!include": "common/parts/dot.jsonl", "vars": {"page": 1}}\n',
            "common/page/empty.png": "",
            "common/parts/dot.jsonl": PART,
            "devices/a/boot.cmd": "run L:/common_page_home.jsonl\nrun L:/own.jsonl\n",
            "devices/a/own.jsonl": '{"page": 2, "id": 1, "obj": "label"}\n',
            "devices/a/config.json": "{}",
            "devices/b/boot.cmd": "run L:/common_page_home.jsonl\n",
            "devices/b/config.json": "{}",
        },
    )
    return root


def _apply(plan):
    trashed = []
    apply_plan(plan, trashed.append)
    return trashed


class TestPlateNames:
    def test_the_folders_are_joined_with_underscores(self, root):
        files = ConfigFiles(root)

        assert files.plate_name(root / "common/page/home.jsonl") == "common_page_home.jsonl"
        assert files.plate_name(root / "devices/a/own.jsonl") == "own.jsonl"
        assert files.plate_name(root / "theme.yaml") is None


class TestRename:
    def test_renaming_a_file_changes_the_references_of_every_device_that_sees_it(self, root):
        plan = plan_move(ConfigFiles(root), root / "common/page/home.jsonl", root / "common/page/start.jsonl")
        _apply(plan)

        assert (root / "common/page/start.jsonl").is_file() and not (root / "common/page/home.jsonl").exists()
        assert (root / "devices/a/boot.cmd").read_text() == "run L:/common_page_start.jsonl\nrun L:/own.jsonl\n"
        assert (root / "devices/b/boot.cmd").read_text() == "run L:/common_page_start.jsonl\n"

    def test_moving_a_folder_renames_the_files_in_it_and_changes_includes_and_images(self, root):
        plan = plan_move(ConfigFiles(root), root / "common/page", root / "common/pages")
        _apply(plan)

        home = (root / "common/pages/home.jsonl").read_text()
        assert '"src": "L:/common_pages_empty.png"' in home
        assert (root / "devices/b/boot.cmd").read_text() == "run L:/common_pages_home.jsonl\n"

    def test_moving_a_part_changes_the_include_paths(self, root):
        plan = plan_move(ConfigFiles(root), root / "common/parts/dot.jsonl", root / "common/page/dot.jsonl")
        _apply(plan)

        assert '"!include": "common/page/dot.jsonl"' in (root / "common/page/home.jsonl").read_text()

    def test_a_longer_name_that_contains_the_old_one_is_not_changed(self, root):
        _write(root, {"devices/a/xown.jsonl": "", "devices/a/boot.cmd": "run L:/own.jsonl\nrun L:/xown.jsonl\n"})
        plan = plan_move(ConfigFiles(root), root / "devices/a/own.jsonl", root / "devices/a/mine.jsonl")

        assert plan.edits[(root / "devices/a/boot.cmd").resolve()] == "run L:/mine.jsonl\nrun L:/xown.jsonl\n"

    def test_a_file_name_that_the_plate_already_has_is_refused(self, root):
        # common/page_home.jsonl would be common_page_home.jsonl too
        with pytest.raises(FileOperationError, match="already has a file named common_page_home.jsonl"):
            plan_move(ConfigFiles(root), root / "common/parts/dot.jsonl", root / "common/page_home.jsonl")

    def test_moving_a_shared_file_to_a_device_that_other_devices_run_is_refused(self, root):
        with pytest.raises(FileOperationError) as error:
            plan_move(ConfigFiles(root), root / "common/page/home.jsonl", root / "devices/a/home.jsonl")

        assert error.value.summary == "The device b couldn't load its pages anymore."
        assert error.value.references == [
            FileReference((root / "devices/b/boot.cmd").resolve(), 1, "run L:/common_page_home.jsonl", "devices/b/boot.cmd:1")
        ]
        assert "devices/b/boot.cmd:1   run L:/common_page_home.jsonl" in error.value.details

    @pytest.mark.parametrize("name", ["", "a b.jsonl", ".hidden.jsonl", "x.cmd"])
    def test_invalid_names_are_refused(self, root, name):
        with pytest.raises(FileOperationError):
            plan_move(ConfigFiles(root), root / "devices/a/own.jsonl", root / "devices/a" / name)

    @pytest.mark.parametrize(
        "path", ["common", "devices", "devices/a", "devices/a/config.json", "devices/a/boot.cmd"]
    )
    def test_the_folders_and_files_the_config_needs_are_protected(self, root, path):
        with pytest.raises(FileOperationError, match="can't be renamed or moved"):
            plan_move(ConfigFiles(root), root / path, root / "devices/a/elsewhere")

    def test_a_too_long_name_is_refused_for_a_file_the_plate_runs_but_not_for_a_part(self, root):
        files = ConfigFiles(root)

        with pytest.raises(FileOperationError, match="it would be a_very_long_name_for_a_page.jsonl: 33 characters"):
            plan_move(files, root / "devices/a/own.jsonl", root / "devices/a/a_very_long_name_for_a_page.jsonl")
        plan = plan_move(files, root / "common/parts/dot.jsonl", root / "common/parts/a_very_long_name_of_a_part.jsonl")
        assert plan.notes == ["Changes the !include paths in: common/page/home.jsonl."]

    def test_moving_a_variable_file_says_where_its_variables_apply(self, root):
        plan = plan_move(ConfigFiles(root), root / "theme.yaml", root / "common/theme.yaml")

        assert any("apply to the files of common" in note for note in plan.notes)


class TestDelete:
    def test_every_device_that_would_break_is_named(self, root):
        _write(root, {"devices/b/boot.cmd": "run L:/common_page_home.jsonl\n// the start page\nrun L:/common_page_home.jsonl\n"})

        with pytest.raises(FileOperationError) as error:
            plan_delete(ConfigFiles(root), root / "common/page")

        assert error.value.summary == "The devices a and b couldn't load their pages anymore."
        assert [(reference.file.parent.name, reference.line) for reference in error.value.references] == [
            ("a", 1),
            ("b", 1),
            ("b", 3),
        ]

    def test_a_file_goes_to_the_trash(self, root):
        _write(root, {"devices/a/unused.jsonl": ""})

        assert _apply(plan_delete(ConfigFiles(root), root / "devices/a/unused.jsonl")) == [
            (root / "devices/a/unused.jsonl").resolve()
        ]

    def test_a_file_that_a_cmd_runs_is_refused(self, root):
        with pytest.raises(FileOperationError) as error:
            plan_delete(ConfigFiles(root), root / "devices/a/own.jsonl")

        assert error.value.summary == "The device a couldn't load its pages anymore."
        assert error.value.references == [
            FileReference((root / "devices/a/boot.cmd").resolve(), 2, "run L:/own.jsonl", "devices/a/boot.cmd:2")
        ]

    def test_an_included_part_is_refused(self, root):
        with pytest.raises(FileOperationError) as error:
            plan_delete(ConfigFiles(root), root / "common/parts")

        assert error.value.summary == "Other files still include it."
        assert [(reference.file.name, reference.line) for reference in error.value.references] == [("home.jsonl", 2)]

    def test_boot_cmd_is_protected_but_the_other_startup_scripts_can_be_deleted(self, root):
        _write(root, {"devices/a/online.cmd": ""})

        with pytest.raises(FileOperationError, match="can't be deleted"):
            plan_delete(ConfigFiles(root), root / "devices/a/boot.cmd")
        assert plan_delete(ConfigFiles(root), root / "devices/a/online.cmd").deletes


class TestCreate:
    def test_a_new_page_file_is_run_from_boot_cmd(self, root):
        plan = plan_create(ConfigFiles(root), root / "devices/a", "new.jsonl", run_from=root / "devices/a/boot.cmd")
        _apply(plan)

        assert (root / "devices/a/new.jsonl").read_text() == ""
        assert (root / "devices/a/boot.cmd").read_text().endswith("run L:/own.jsonl\nrun L:/new.jsonl\n")

    def test_a_folder(self, root):
        _apply(plan_create(ConfigFiles(root), root / "common", "dialogs"))

        assert (root / "common/dialogs").is_dir()

    def test_only_variable_files_go_into_the_root(self, root):
        with pytest.raises(FileOperationError, match="Only variable files"):
            plan_create(ConfigFiles(root), root, "page.jsonl")
        assert plan_create(ConfigFiles(root), root, "colors.yaml").creates

    def test_an_existing_name_is_refused(self, root):
        with pytest.raises(FileOperationError, match="already exists"):
            plan_create(ConfigFiles(root), root / "devices/a", "own.jsonl")


def test_the_targets_of_a_move_are_the_folders_of_common_and_the_device(root):
    files = ConfigFiles(root)

    targets = [files.config_path(path) if path != files.root else "." for path in move_targets(files, root / "common/page", root / "devices/a")]

    assert targets == ["common/parts", "devices/a"]
