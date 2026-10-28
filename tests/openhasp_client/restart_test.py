from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client import openhasp
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase


class TestWaitForRestart(TestBase):
    def _client(self, tmp_path, monkeypatch, answers: list):
        """:param answers: what the plate answers to each request for its files, in order: a list of files, or an exception"""
        monkeypatch.setattr(openhasp, "RESTART_POLL_SECONDS", 0)
        device = ConfigManager(self.cfg_root, tmp_path, VariableManager(self.cfg_root)).analyze()[0]
        client = OpenHaspClient(device)

        async def get_files():
            answer = answers.pop(0) if answers else []
            if isinstance(answer, Exception):
                raise answer
            return answer

        monkeypatch.setattr(client, "get_files", get_files)
        return client

    async def test_the_plate_restarted_when_it_answers_again_after_it_was_gone(self, tmp_path, monkeypatch):
        # still running, gone, starting (an empty answer), back
        client = self._client(tmp_path, monkeypatch, [["a.jsonl"], OSError("gone"), AttributeError("empty"), ["a.jsonl"]])

        assert await client.wait_for_restart(timeout=10)

    async def test_a_plate_that_never_went_away_did_not_restart(self, tmp_path, monkeypatch):
        client = self._client(tmp_path, monkeypatch, [])

        assert not await client.wait_for_restart(timeout=0.01)
