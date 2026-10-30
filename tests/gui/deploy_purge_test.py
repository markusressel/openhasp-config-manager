from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from openhasp_config_manager.gui.qt.window import draft_actions  # noqa: E402
from tests.gui.helpers import create_editor_cfg_root, wait_until  # noqa: E402


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    return create_editor_cfg_root(tmp_path)


@pytest.fixture
def plate(monkeypatch):
    """The files on the plate, and the deployments (whether each purged), without a plate"""
    state = {"files": [], "deployments": [], "confirmations": []}

    async def obsolete_files(config_manager, device):
        return list(state["files"])

    async def deploy_device(config_manager, device, purge=False, show_diff=False, restart=False):
        state["deployments"].append(purge)
        return True

    monkeypatch.setattr(draft_actions, "obsolete_files", obsolete_files)
    monkeypatch.setattr(draft_actions, "deploy_device", deploy_device)
    return state


def _confirm(window, monkeypatch, plate, answer: bool):
    def confirm_purge(name, files):
        plate["confirmations"].append((name, files))
        return answer

    monkeypatch.setattr(window.draft_actions, "confirm_purge", confirm_purge)


class TestDeployAndRemoveOtherFiles:
    def test_lists_the_files_and_deletes_them_when_confirmed(self, window, plate, monkeypatch):
        # GIVEN
        plate["files"] = ["old_page.jsonl", "old_font.ttf"]
        _confirm(window, monkeypatch, plate, True)

        # WHEN
        window.action_deploy_purge.trigger()

        # THEN
        wait_until(lambda: plate["deployments"])
        assert plate["confirmations"] == [("test_device", ["old_page.jsonl", "old_font.ttf"])]
        assert plate["deployments"] == [True]

    def test_nothing_is_deployed_when_it_is_cancelled(self, window, plate, monkeypatch):
        # GIVEN
        plate["files"] = ["old_page.jsonl"]
        _confirm(window, monkeypatch, plate, False)

        # WHEN
        window.action_deploy_purge.trigger()

        # THEN
        wait_until(lambda: plate["confirmations"])
        wait_until(lambda: not window.page_layout_editor_widget.busy.busy)
        assert plate["deployments"] == []

    def test_without_other_files_it_deploys_without_asking(self, window, plate, monkeypatch):
        # GIVEN
        _confirm(window, monkeypatch, plate, True)

        # WHEN
        window.action_deploy_purge.trigger()

        # THEN
        wait_until(lambda: plate["deployments"])
        assert plate["confirmations"] == []
        assert plate["deployments"] == [False]

    def test_deploy_does_not_purge(self, window, plate):
        # WHEN
        window.action_deploy.trigger()

        # THEN
        wait_until(lambda: plate["deployments"])
        assert plate["deployments"] == [False]


class TestDeployActions:
    def test_are_disabled_while_the_editor_is_busy(self, window):
        # WHEN
        window.page_layout_editor_widget.busy.enter()

        # THEN
        assert not window.action_deploy.isEnabled()
        assert not window.action_deploy_purge.isEnabled()
        window.page_layout_editor_widget.busy.leave()
        assert window.action_deploy.isEnabled() and window.action_deploy_purge.isEnabled()
