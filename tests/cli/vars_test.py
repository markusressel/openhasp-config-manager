from pathlib import Path

import pytest
from click.testing import CliRunner

from openhasp_config_manager.cli import cli
from tests.helpers import copy_test_config


@pytest.fixture
def cfg_root(tmp_path) -> Path:
    return copy_test_config(
        tmp_path, {"computed.vars.yaml": 'margin: 4\ncard:\n  w: "{{ device.screen.width - margin * 2 }}"\n'}
    )


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

        # THEN: the variables that need it are printed as they are written
        assert result.exit_code == 0, result.output
        assert "card.w: {{ device.screen.width - margin * 2 }}\n" in result.output
        assert "margin: 4\n" in result.output

    def test_a_path_outside_of_the_devices_with_a_device(self, cfg_root):
        # GIVEN: a variable of the device folder replaces the global one, like it does for the files of the common folder
        (cfg_root / "devices/test_device/margin.vars.yaml").write_text("margin: 10\n")

        # WHEN
        result = CliRunner().invoke(cli, ["vars", "-c", str(cfg_root), "-p", "common", "-d", "test_device"])

        # THEN
        assert result.exit_code == 0, result.output
        assert "card.w: 460\n" in result.output

    def test_an_unknown_device(self, cfg_root):
        # WHEN
        result = CliRunner().invoke(cli, ["vars", "-c", str(cfg_root), "-p", "common", "-d", "nope"])

        # THEN
        assert "Unknown device: nope" in result.output
