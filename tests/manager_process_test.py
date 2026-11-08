import json
from pathlib import Path

import pytest

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.processing.variables import VariableManager
from tests import TestBase
from tests.helpers import copy_test_config


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
        cfg_root = copy_test_config(
            tmp_path, {"common/parts/dot.jsonl": '{"page": 9, "id": "{{ id }}", "obj": "obj", "x": "{{ id * 2 }}"}\n'}
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


def _set_file_name_limit(cfg_root: Path, value):
    config_file = cfg_root / "devices" / "test_device" / "config.json"
    config = json.loads(config_file.read_text())
    config["openhasp_config_manager"]["device"]["max_file_name_length"] = value
    config_file.write_text(json.dumps(config))


def _manager(cfg_root: Path, output: Path) -> ConfigManager:
    variable_manager = VariableManager(cfg_root)
    variable_manager.read()
    return ConfigManager(cfg_root, output, variable_manager)


class TestFileNameLimit(TestBase):
    def test_the_limit_is_255_unless_the_device_sets_one(self, tmp_path):
        cfg_root = copy_test_config(tmp_path)
        (device,) = _manager(cfg_root, tmp_path / "output").analyze()
        assert device.config.openhasp_config_manager.device.max_file_name_length == 255

        _set_file_name_limit(cfg_root, 31)
        (device,) = _manager(cfg_root, tmp_path / "output").analyze()
        assert device.config.openhasp_config_manager.device.max_file_name_length == 31

    @pytest.mark.parametrize("value", [0, -1, "31", 31.5, True])
    def test_a_limit_that_is_not_a_positive_whole_number_is_refused(self, tmp_path, value):
        cfg_root = copy_test_config(tmp_path)
        _set_file_name_limit(cfg_root, value)

        with pytest.raises(Exception, match="max_file_name_length must be a positive whole number"):
            _manager(cfg_root, tmp_path / "output").analyze()

    def test_a_deploy_refuses_names_longer_than_the_limit_of_the_device(self, tmp_path):
        # GIVEN: a page of 32 characters on the plate, which fits the default but not a limit of 31
        cfg_root = copy_test_config(
            tmp_path, {"devices/test_device/home/thirty_two_characters.jsonl": '{"page": 1, "id": 9}\n'}
        )
        home_cmd = cfg_root / "devices" / "test_device" / "home.cmd"
        home_cmd.write_text(home_cmd.read_text().rstrip("\n") + "\nrun L:/home_thirty_two_characters.jsonl\n")
        assert len("home_thirty_two_characters.jsonl") == 32
        for device in _manager(cfg_root, tmp_path / "output").analyze():
            _manager(cfg_root, tmp_path / "output").process(device)

        # WHEN
        _set_file_name_limit(cfg_root, 31)
        manager = _manager(cfg_root, tmp_path / "output2")

        # THEN
        with pytest.raises(Exception, match="must not exceed 31 characters, but was 32: home_thirty_two_characters.jsonl"):
            for device in manager.analyze():
                manager.process(device)
