import json
from pathlib import Path
from typing import Dict

from openhasp_config_manager.cli.common import _create_config_manager, _analyze_and_filter
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.ui.util import success, error


async def c_state(config_dir: Path, device: str, object: str, state: str):
    try:
        state_json = json.loads(state)
        if not isinstance(state_json, Dict):
            raise Exception("State must be a JSON object.")

        config_manager = _create_config_manager(config_dir, Path("./nonexistent"))
        filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)
        if len(filtered_devices) <= 0:
            raise Exception(f"No device matches the filter: {device}")
        for device in filtered_devices:
            client = OpenHaspClient(device)
            await client.set_object_properties(object, state_json)
        success("Done!")
    except Exception as ex:
        error(str(ex))
