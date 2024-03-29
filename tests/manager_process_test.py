from pathlib import Path

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase


class TestConfigManager(TestBase):

    def test_process_whole_config(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        manager = ConfigManager(self.cfg_root, tmp_path, variable_manager)

        devices = manager.analyze()

        # WHEN
        for device in devices:
            manager.process(device)

        # THEN
        file_count = 0
        for file in tmp_path.rglob("*.jsonl"):
            file_count += 1
            content = file.read_text()
            assert len(content) > 0
            for line in content.splitlines():
                assert line.startswith("{")
                assert line.endswith("}")

        assert file_count > 0

    def test_image_file_is_copied_when_referenced_in_jsonl_src(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        manager = ConfigManager(self.cfg_root, tmp_path, variable_manager)

        devices = manager.analyze()

        # WHEN
        for device in devices:
            manager.process(device)

        # THEN
        file_count = 0
        for file in tmp_path.rglob("*.png"):
            file_count += 1
            content = file.read_bytes()
            assert len(content) > 0

        assert file_count > 0

    def test_global_variable(self, tmp_path):
        # GIVEN
        variable_manager = VariableManager(self.cfg_root)
        manager = ConfigManager(self.cfg_root, tmp_path, variable_manager)
        devices = manager.analyze()

        # WHEN
        for device in devices:
            manager.process(device)

        # THEN
        home_page_file = Path(tmp_path, "test_device", "home_page.jsonl")
        content = home_page_file.read_text()
        assert "global_var_value" in content
        assert "global_value" not in content
        assert "test_device_value" in content
