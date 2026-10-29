import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from openhasp_config_manager.cli import cli


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    root = tmp_path / "cfg"
    shutil.copytree(Path(__file__).parent.parent / "_test_cfg_root", root)
    (root / "computed.vars.yaml").write_text('margin: 4\ncard:\n  w: "{{ device.screen.width - margin * 2 }}"\n')
    return root


class TestVars:
    def test_prints_the_computed_values_with_the_device_of_the_path(self, cfg_root):
        # WHEN
        result = CliRunner().invoke(cli, ["vars", "-c", str(cfg_root), "-p", "devices/test_device/home"])

        # THEN: the screen of the test device is rotated, 480 wide
        assert result.exit_code == 0, result.output
        assert "card.w: 472\n" in result.output
        assert "margin: 4\n" in result.output
        assert not any(line.startswith("device") for line in result.output.splitlines())

    def test_a_path_outside_of_the_devices_has_no_device(self, cfg_root):
        # WHEN
        result = CliRunner().invoke(cli, ["vars", "-c", str(cfg_root), "-p", "common"])

        # THEN
        assert "Unknown variable 'device' in the variable 'card.w'" in result.output
