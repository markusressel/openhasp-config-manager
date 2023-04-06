from pathlib import Path

from openhasp_config_manager.cli.common import _create_config_manager, _analyze_and_filter, _cmd
from openhasp_config_manager.ui.util import success, error


async def c_cmd(config_dir: Path, device: str, command: str, payload: str):
    try:
        config_manager = _create_config_manager(config_dir, Path("./nonexistent"))
        filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)

        if len(filtered_devices) <= 0:
            raise Exception(f"No device matches the filter: {device}")

        for device in filtered_devices:
            await _cmd(device, command, payload)
        success("Done!")
    except Exception as ex:
        error(str(ex))
