from pathlib import Path
from typing import Tuple, List

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.ui.util import info


async def _generate(config_manager: ConfigManager, device: Device):
    info(f"Generating output for '{device.name}'...")
    try:
        config_manager.process(device)
    except Exception as ex:
        raise Exception(f"Error generating output for {device.name}: {ex.__class__.__name__} {ex}")


async def _upload(device: Device, output_dir: Path, purge: bool, show_diff: bool):
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
    from openhasp_config_manager.uploader import ConfigUploader

    client = OpenHaspClient(device)
    uploader = ConfigUploader(output_dir, client)

    info(f"Uploading files to device '{device.name}'...")
    return uploader.upload(device, purge, show_diff)


async def _deploy(config_manager: ConfigManager, device: Device, output_dir: Path, purge: bool, show_diff: bool):
    await _generate(config_manager, device)
    changed = await _upload(device, output_dir, purge, show_diff)
    # _cmd(config_dir, device="touch_down_1", command="reboot", payload="")
    # _reload(config_dir, device)
    if changed:
        info(f"Rebooting {device.name} to apply changes")
        await _reboot(device)
    else:
        info(f"No changes detected for {device.name}, device is already up-to-date")


async def _reload(device: Device):
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    client = OpenHaspClient(device)
    await client.command("clearpage", "all")
    await client.command("run", "L:/boot.cmd")


async def _reboot(device: Device):
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    client = OpenHaspClient(device)
    info(f"Rebooting {device.name}...")
    client.reboot()


async def _cmd(device: Device, command: str, payload: str):
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    client = OpenHaspClient(device)
    info(f"Sending command {command} to {device.name}...")
    await client.command(command, payload)


def _create_config_manager(config_dir, output_dir) -> ConfigManager:
    variable_manager = VariableManager(cfg_root=config_dir)
    config_manager = ConfigManager(
        cfg_root=config_dir,
        output_root=output_dir,
        variable_manager=variable_manager
    )
    return config_manager


def _analyze_and_filter(config_manager: ConfigManager, device_filter: str or None) -> Tuple[List[Device], List[Device]]:
    """

    :param config_manager:
    :param device_filter:
    :return: (matching_devices, ignored_devices)
    """
    info(f"Analyzing files in '{config_manager.cfg_root}'...")
    devices = config_manager.analyze()
    devices = list(sorted(devices, key=lambda x: x.name))
    device_names = list(map(lambda x: x.name, devices))
    info(f"Found devices: {', '.join(device_names)}")

    filtered_devices = []
    ignored_devices = []
    if device_filter is not None:
        filtered_devices = list(filter(lambda x: x.name == device_filter, devices))
        ignored_devices = list(filter(lambda x: x not in filtered_devices, devices))
    else:
        filtered_devices = devices

    return filtered_devices, ignored_devices
