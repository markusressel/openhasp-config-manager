"""Helpers of the GUI tests that need the main window: waiting for it, its state file, a config directory to edit."""

import json
import shutil
from pathlib import Path

import pytest

# the file of the editor tests: a label and a button on page 9
EDITOR_JSONL = """{"page": 9, "id": 1, "obj": "label", "text": "A", "x": 10}
{"page": 9, "id": 2, "obj": "btn", "text": "B"}
"""


def wait_until(condition, timeout_ms: int = 5000):
    """Process the events of Qt until the condition is true. :raises AssertionError: if it isn't in time"""
    from PyQt6.QtTest import QTest

    for _ in range(timeout_ms // 10):
        if condition():
            return
        QTest.qWait(10)
    raise AssertionError("timed out")


def qwait(ms: int):
    from PyQt6.QtTest import QTest

    QTest.qWait(ms)


def create_editor_cfg_root(tmp_path: Path) -> Path:
    """A copy of the test config whose device loads only `editor.jsonl` (`EDITOR_JSONL`). Skips without watchdog."""
    pytest.importorskip("watchdog")
    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    device = root / "devices" / "test_device"
    (device / "editor.jsonl").write_text(EDITOR_JSONL)
    (device / "boot.cmd").write_text("run L:/editor.jsonl\n")
    return root


def x_of_label(window) -> int:
    """:return: the x of the label of `EDITOR_JSONL` in the draft"""
    [component] = window.session.components
    return window.session.working_objects[component.key][0]["x"]


def gui_state(cfg_root: Path) -> dict:
    """:return: the state file the GUI writes, {} if there is none yet"""
    try:
        return json.loads((cfg_root / ".openhasp-config-manager" / "gui-state.json").read_text())
    except FileNotFoundError:
        return {}
