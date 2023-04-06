import asyncio
from pathlib import Path

from openhasp_config_manager.cli.common import _create_config_manager, _analyze_and_filter
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.ui.util import success, error, info


async def c_listen(config_dir: Path, device: str, path: str):
    try:
        config_manager = _create_config_manager(config_dir, Path("./nonexistent"))
        filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)
        if len(filtered_devices) <= 0:
            raise Exception(f"No device matches the filter: {device}")
        for device in filtered_devices:
            client = OpenHaspClient(device)

            async def on_message(topic: str, payload: bytes):
                info(f"{topic}: {payload.decode('utf-8')}")

            await client.listen_event(path, on_message)
        asyncio.get_event_loop().run_forever()
        success("Done!")
    except Exception as ex:
        error(str(ex))
