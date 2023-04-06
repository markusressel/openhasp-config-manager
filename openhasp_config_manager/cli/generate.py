from pathlib import Path

from openhasp_config_manager.cli.common import _create_config_manager, _analyze_and_filter, _generate
from openhasp_config_manager.ui.util import warn, success, error


async def c_generate(config_dir: Path, output_dir: Path, device: str):
    try:
        config_manager = _create_config_manager(config_dir, output_dir)
        filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)

        if len(filtered_devices) <= 0:
            if device is None:
                raise Exception("No devices found.")
            else:
                raise Exception(f"No device matches the filter: {device}")

        if len(ignored_devices) > 0:
            ignored_devices_names = list(map(lambda x: x.name, ignored_devices))
            warn(f"Skipping devices: {', '.join(ignored_devices_names)}")

        for device in filtered_devices:
            await _generate(config_manager, device)

        success("Done!")
    except Exception as ex:
        error(str(ex))
