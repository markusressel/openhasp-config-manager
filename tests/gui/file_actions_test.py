"""The file operations of the Files tree in the window: the context menu, the dialogs, and how the editor follows them."""

from pathlib import Path

import pytest

from tests import TestBase
from tests.gui.helpers import create_editor_cfg_root, wait_until


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    return create_editor_cfg_root(tmp_path)


@pytest.fixture
def answers(monkeypatch):
    """Answers the dialogs: the name to type, and the button of the question that carries the plan out."""
    from PyQt6.QtWidgets import QInputDialog, QMessageBox

    answers = {"name": None, "confirm": True, "warnings": [], "refusals": [], "open": False}
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *args: (answers["name"], answers["name"] is not None)))

    def exec_box(box):
        roles = {box.buttonRole(button): button for button in box.buttons()}
        if QMessageBox.ButtonRole.AcceptRole not in roles:
            # a refusal: its "Open ..." buttons are action buttons
            answers["refusals"].append((box.text(), box.informativeText(), [button.text() for button in box.buttons()]))
            box.clickedButton = lambda: roles.get(QMessageBox.ButtonRole.ActionRole) if answers["open"] else None
            return 0
        answers["question"] = box.text()
        box.clickedButton = lambda: roles[QMessageBox.ButtonRole.AcceptRole] if answers["confirm"] else None
        return 0

    monkeypatch.setattr(QMessageBox, "exec", exec_box)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda _parent, _title, text: answers["warnings"].append(text)))
    return answers


def _names(window):
    from PyQt6.QtWidgets import QTreeWidgetItemIterator

    result = []
    iterator = QTreeWidgetItemIterator(window.file_tree_widget.tree)
    while iterator.value():
        result.append(iterator.value().text(0))
        iterator += 1
    return result


class TestMenu(TestBase):
    def test_what_the_config_needs_cant_be_renamed_moved_or_deleted(self, window, cfg_root):
        tree = window.file_tree_widget
        device = cfg_root / "devices" / "test_device"

        def reasons(path):
            return {action: reason for action, _title, _icon, reason in tree.file_actions(path)}

        assert reasons(device)["rename"] == "The folder of a device is the device: its name is the name of the plate."
        assert reasons(device)["new_file"] is None
        assert reasons(device / "boot.cmd")["rename"] == "The plate runs boot.cmd by its name."
        assert reasons(device / "boot.cmd")["delete"] is not None
        assert reasons(device / "config.json")["move"] == "config.json holds the settings of the plate."
        assert reasons(cfg_root)["new_folder"] is not None
        assert set(reasons(device / "editor.jsonl").values()) == {None}


class TestOperations(TestBase):
    def test_a_rename_changes_the_run_line_and_the_editor_follows(self, window, cfg_root, answers):
        # GIVEN
        device = cfg_root / "devices" / "test_device"
        window.source_sync.open_file(device / "editor.jsonl")
        answers["name"] = "pages.jsonl"

        # WHEN
        window.file_actions.rename(device / "editor.jsonl")

        # THEN
        assert (device / "boot.cmd").read_text() == "run L:/pages.jsonl\n"
        assert "Changes the references (L:/...) in: devices/test_device/boot.cmd." in answers["question"]
        wait_until(lambda: "pages.jsonl" in _names(window))
        assert "editor.jsonl" not in _names(window)
        assert (device / "pages.jsonl").resolve() in [path.resolve() for path in window.source_editor.open_files]
        wait_until(lambda: window.session is not None and window.session.components[0].path.name == "pages.jsonl")

    def test_a_new_page_file_is_run_from_boot_cmd_and_opened(self, window, cfg_root, answers):
        # GIVEN
        device = cfg_root / "devices" / "test_device"
        answers["name"] = "more.jsonl"

        # WHEN
        window.file_actions.new_file(device)

        # THEN
        assert (device / "more.jsonl").is_file()
        assert (device / "boot.cmd").read_text() == "run L:/editor.jsonl\nrun L:/more.jsonl\n"
        assert (device / "more.jsonl").resolve() in [path.resolve() for path in window.source_editor.open_files]

    def test_nothing_changes_when_the_question_is_cancelled(self, window, cfg_root, answers):
        device = cfg_root / "devices" / "test_device"
        answers["name"] = "pages.jsonl"
        answers["confirm"] = False

        window.file_actions.rename(device / "editor.jsonl")

        assert (device / "editor.jsonl").is_file() and not (device / "pages.jsonl").exists()

    def test_files_with_unsaved_changes_of_the_draft_are_not_changed(self, window, cfg_root, answers):
        # GIVEN
        device = cfg_root / "devices" / "test_device"
        [component] = window.session.components
        window.session.set_source_value(window.session.working_objects[component.key][0], "x", 20)
        answers["name"] = "pages.jsonl"

        # WHEN
        window.file_actions.rename(device / "editor.jsonl")

        # THEN
        assert answers["warnings"] == ["The draft has unsaved changes in files this changes. Save or revert the draft first."]
        assert (device / "editor.jsonl").is_file()

    def test_a_refused_operation_says_why_and_opens_the_line_to_change(self, window, cfg_root, answers):
        # GIVEN
        device = cfg_root / "devices" / "test_device"
        answers["open"] = True

        # WHEN
        window.file_actions.delete(device / "editor.jsonl")

        # THEN
        [(summary, details, buttons)] = answers["refusals"]
        assert summary == "<b>The device test_device couldn't load its pages anymore.</b>"
        assert "<code>run L:/editor.jsonl</code><br><span style='color:gray'>devices/test_device/boot.cmd:1</span>" in details
        assert "Open boot.cmd" in buttons
        assert (device / "editor.jsonl").is_file()
        assert window.source_editor.current_file == (device / "boot.cmd").resolve()
