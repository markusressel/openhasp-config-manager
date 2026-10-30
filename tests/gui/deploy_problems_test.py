from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

from openhasp_config_manager.check import Issue  # noqa: E402
from openhasp_config_manager.gui.domain.problems import Severity  # noqa: E402
from openhasp_config_manager.gui.qt.widgets.deploy_problems import DeployProblemsDialog  # noqa: E402
from tests.gui.helpers import create_editor_cfg_root, wait_until  # noqa: E402
from tests.helpers import DEVICE_DIR, TEST_DEVICE  # noqa: E402

ISSUE = Issue(
    Severity.ERROR,
    "Unknown variable 'pages' in the variable 'page_index'",
    device=TEST_DEVICE,
    file="common/room/vars.yaml",
    line=2,
    hints=("No YAML file defines 'pages'.",),
)


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    return create_editor_cfg_root(tmp_path)


def _texts(dialog) -> list:
    return [label.text() for label in dialog.findChildren(QLabel)]


class TestDialog:
    def test_shows_the_error_where_it_is_and_how_to_fix_it(self, qapp, tmp_path):
        # WHEN
        dialog = DeployProblemsDialog(TEST_DEVICE, tmp_path, [ISSUE])

        # THEN
        texts = _texts(dialog)
        assert dialog.windowTitle() == f"Can't deploy {TEST_DEVICE}"
        assert "Unknown variable &#x27;pages&#x27; in the variable &#x27;page_index&#x27;" in texts
        assert '<a href="0">common/room/vars.yaml:2</a>' in texts
        assert "• No YAML file defines &#x27;pages&#x27;." in texts

    def test_the_location_opens_the_file_at_the_line(self, qapp, tmp_path):
        # GIVEN
        dialog = DeployProblemsDialog(TEST_DEVICE, tmp_path, [ISSUE])
        opened = []
        dialog.openRequested.connect(lambda path, line: opened.append((path, line)))
        [link] = [label for label in dialog.findChildren(QLabel) if label.text().startswith("<a ")]

        # WHEN
        link.linkActivated.emit("0")

        # THEN
        assert opened == [(tmp_path / "common/room/vars.yaml", 2)]


def _dialogs():
    return [
        widget for widget in QApplication.topLevelWidgets() if isinstance(widget, DeployProblemsDialog) and widget.isVisible()
    ]


class TestDeploy:
    def test_files_that_cant_be_processed_open_the_dialog_and_nothing_is_uploaded(self, window, cfg_root, monkeypatch):
        # GIVEN: a variable that nothing defines
        (cfg_root / DEVICE_DIR / "vars.yaml").write_text('page_index: "{{ pages.room.index }}"\n')
        uploads = []
        monkeypatch.setattr(
            "openhasp_config_manager.deployment.ConfigUploader.upload_changes",
            lambda *args, **kwargs: uploads.append(args),
        )

        # WHEN
        window.draft_actions.deploy()

        # THEN
        wait_until(lambda: _dialogs())
        [dialog] = _dialogs()
        assert f"{DEVICE_DIR}/vars.yaml:1" in " ".join(_texts(dialog))
        assert uploads == []
        dialog.close()

    def test_the_location_opens_the_file_in_the_text_editor(self, window, cfg_root):
        # GIVEN
        variables = cfg_root / DEVICE_DIR / "vars.yaml"
        variables.write_text('page_index: "{{ pages.room.index }}"\n')
        window.draft_actions.deploy()
        wait_until(lambda: _dialogs())
        [dialog] = _dialogs()

        # WHEN
        dialog.openRequested.emit(variables.resolve(), 1)

        # THEN
        wait_until(lambda: window.source_editor.current_file == variables.resolve())
        dialog.close()
