import json
import shutil
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

    def test_a_file_that_is_only_included_is_not_deployed_on_its_own(self, tmp_path):
        # GIVEN: a page includes a part that no .cmd file runs
        cfg_root = tmp_path / "cfg"
        shutil.copytree(self.cfg_root, cfg_root)
        (cfg_root / "common" / "parts").mkdir()
        (cfg_root / "common" / "parts" / "dot.jsonl").write_text(
            '{"page": 9, "id": "{{ id }}", "obj": "obj", "x": "{{ id * 2 }}"}\n'
        )
        (cfg_root / "devices" / "test_device" / "home" / "dots.jsonl").write_text(
            '{"!include": "common/parts/dot.jsonl", "for": {"id": [1, 2]}}\n'
        )
        home_cmd = cfg_root / "devices" / "test_device" / "home.cmd"
        home_cmd.write_text(home_cmd.read_text().rstrip("\n") + "\nrun L:/home_dots.jsonl\n")
        variable_manager = VariableManager(cfg_root)
        variable_manager.read()
        manager = ConfigManager(cfg_root, tmp_path / "output", variable_manager)

        # WHEN
        for device in manager.analyze():
            manager.process(device)

        # THEN
        output = tmp_path / "output" / "test_device"
        assert not (output / "common_parts_dot.jsonl").exists()
        assert [json.loads(line) for line in (output / "home_dots.jsonl").read_text().splitlines()] == [
            {"page": 9, "id": 1, "obj": "obj", "x": 2},
            {"page": 9, "id": 2, "obj": "obj", "x": 4},
        ]
