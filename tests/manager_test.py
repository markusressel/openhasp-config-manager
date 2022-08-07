from pathlib import Path

from openhasp_config_manager.manager import ConfigManager
from tests import TestBase


class TestConfigManager(TestBase):

    def test_process_whole_config(self, tmp_path):
        manager = ConfigManager(self.cfg_root, tmp_path)

        devices = manager.analyze()
        manager.process(devices)

        file_count = 0
        for file in tmp_path.rglob("*.jsonl"):
            file_count += 1
            content = file.read_text()
            assert len(content) > 0
            for line in content.splitlines():
                assert line.startswith("{")
                assert line.endswith("}")

        assert file_count > 0

    def test_global_variable(self, tmp_path):
        # GIVEN
        manager = ConfigManager(self.cfg_root, tmp_path)
        devices = manager.analyze()

        # WHEN
        manager.process(devices)

        # THEN
        home_page_file = Path(tmp_path, "test_device", "home_page.jsonl")
        content = home_page_file.read_text()
        assert "global_var_value" in content
        assert "global_value" not in content
        assert "test_device_value" in content
