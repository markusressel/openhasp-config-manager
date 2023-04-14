from pathlib import Path

from openhasp_config_manager.cli.common import _create_config_manager, _analyze_and_filter
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.ui.util import error, info


async def c_logs(config_dir: Path, device: str):
    try:
        config_manager = _create_config_manager(config_dir, Path("./nonexistent"))
        filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)
        if len(filtered_devices) <= 0:
            raise Exception(f"No device matches the filter: {device}")
        if len(filtered_devices) > 1:
            raise Exception(f"More than one device matches the filter: {device}")
        info(f"Listening to logs of: {filtered_devices[0].name}")
        for device in filtered_devices:
            client = OpenHaspClient(device)
            await client.logs()
    except Exception as ex:
        error(str(ex))
