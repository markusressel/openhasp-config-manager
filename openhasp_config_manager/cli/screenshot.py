from pathlib import Path

from openhasp_config_manager.cli.common import _create_config_manager, _analyze_and_filter
from openhasp_config_manager.ui.util import error, success, info


async def c_screenshot(config_dir: Path, device: str, output: Path):
    try:
        config_manager = _create_config_manager(config_dir, Path("./nonexistent"))
        filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)

        if len(filtered_devices) <= 0:
            raise Exception(f"No device matches the filter: {device}")

        for device in filtered_devices:
            from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
            from openhasp_config_manager.uploader import ConfigUploader

            client = OpenHaspClient(device)
            try:
                info(f"Taking screenshot of device '{device.name}'...")
                screenshot = client.take_screenshot()
                image_file_path = Path(output, f"{device.name}.bmp")
                image_file_path.write_bytes(screenshot)
            except Exception as ex:
                raise Exception(f"Error taking screenshot of device '{device.name}': {ex}")

        success("Done!")
    except Exception as ex:
        error(str(ex))
