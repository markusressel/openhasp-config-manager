from openhasp_config_manager.cli.screenshot import c_screenshot
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from tests import TestBase


class TestScreenshot(TestBase):
    async def test_screenshot_is_written_to_the_output_directory(self, tmp_path, monkeypatch):
        # GIVEN
        async def take_screenshot(client):
            return b"BM-image"

        monkeypatch.setattr(OpenHaspClient, "take_screenshot", take_screenshot)

        # WHEN
        await c_screenshot(self.cfg_root, "test_device", tmp_path)

        # THEN
        assert (tmp_path / "test_device.bmp").read_bytes() == b"BM-image"
