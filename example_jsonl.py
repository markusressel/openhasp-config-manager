import asyncio
from pathlib import Path
from typing import List, Dict

from orjson import orjson

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.processing.variables import VariableManager


async def main():
    """
    Example to set dynamically clear and apply all pages specified in the
    openhasp-configs for a given device using OpenHaspClient.
    """
    config_dir = Path("./openhasp-configs")
    output_dir = Path("./output")

    variable_manager = VariableManager(cfg_root=config_dir)
    config_manager = ConfigManager(
        cfg_root=config_dir,
        output_root=output_dir,
        variable_manager=variable_manager
    )

    devices = config_manager.analyze()
    device: Device = next(filter(lambda x: x.name == "wt32sc01plus_2", devices))
    device_processor = config_manager.create_device_processor(device)
    # load jsonl component objects
    boot_cmd_component = next(filter(lambda x: x.name == "boot.cmd", device.cmd), None)
    ordered_jsonl_components = config_manager.determine_device_jsonl_component_order_for_cmd(device, boot_cmd_component)
    loaded_objects: List[Dict] = []
    for jsonl_component in ordered_jsonl_components:
        normalized_jsonl_component = device_processor.normalize(device, jsonl_component)
        objects_in_jsonl = normalized_jsonl_component.splitlines()
        loaded_objects.extend(list(map(orjson.loads, objects_in_jsonl)))

    # apply page 0 objects last (on top)
    loaded_objects = sorted(loaded_objects, key=lambda x: x.get("page", 0))

    client = OpenHaspClient(device)

    await client.clear_page(0)
    await client.clear_page(1)
    await client.clear_page(2)
    await client.clear_page(3)

    for jsonl_object in loaded_objects:
        if jsonl_object.get("page", None) not in [0, 1, 2, 3]:
            continue
        print(f"Sending {jsonl_object}")
        await client.command("jsonl", jsonl_object)


if __name__ == '__main__':
    asyncio.run(main())
