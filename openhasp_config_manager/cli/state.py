from pathlib import Path
from openhasp_config_manager.cli.common import _create_config_manager, _analyze_and_filter
from openhasp_config_manager.ui.util import success, error

async def c_state(config_dir: Path, device: str, object: str, state: str):
    try:
        config_manager = _create_config_manager(config_dir, Path("./nonexistent"))
        filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)
        if len(filtered_devices) <= 0:
            raise Exception(f"No device matches the filter: {device}")
        for device in filtered_devices:
            # TODO: call openhasp client
            pass
        success("Done!")
    except Exception as ex:
        error(str(ex))
