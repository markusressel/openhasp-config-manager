from pathlib import Path
from typing import Tuple, List

from openhasp_config_manager.console import info
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.processing.variables import VariableManager


async def _generate(config_manager: ConfigManager, device: Device):
    info(f"Generating output for '{device.name}'...")
    try:
        config_manager.process(device)
    except Exception as ex:
        raise Exception(
            f"Error generating output for {device.name}: {ex.__class__.__name__} {ex}\n"
            f"Run `openhasp-config-manager check -d {device.name}` to see all errors and how to fix them."
        )


async def _upload(device: Device, output_dir: Path, purge: bool, show_diff: bool):
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
    from openhasp_config_manager.uploader import ConfigUploader

    client = OpenHaspClient(device)
    uploader = ConfigUploader(output_dir, client)

    info(f"Uploading files to device '{device.name}'...")
    return await uploader.upload(device, purge, show_diff)


async def _deploy(config_manager: ConfigManager, device: Device, purge: bool, show_diff: bool, restart: bool = False):
    from openhasp_config_manager.deployment import deploy_device

    await deploy_device(config_manager, device, purge=purge, show_diff=show_diff, restart=restart)


async def _reload(device: Device):
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    client = OpenHaspClient(device)
    await client.restore_from_files()


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
        variable_manager=variable_manager,
    )
    return config_manager


def _analyze_and_filter(config_manager: ConfigManager, device_filter: str | None) -> Tuple[List[Device], List[Device]]:
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
