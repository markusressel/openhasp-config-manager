import asyncio

from openhasp_config_manager.console import info
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.uploader import ConfigUploader


async def deploy_device(config_manager: ConfigManager, device: Device, purge: bool = False, show_diff: bool = False) -> bool:
    """
    Deploy the files of a device as they are on disk: generate its output, upload what changed and restart the plate
    if anything changed, so it loads the new files.
    :param purge: remove files from the plate that are not part of the generated output
    :param show_diff: print a diff for each changed file
    :return: whether anything changed
    """
    info(f"Generating output for '{device.name}'...")
    try:
        await asyncio.to_thread(config_manager.process, device)
    except Exception as ex:
        raise Exception(f"Error generating output for {device.name}: {ex.__class__.__name__} {ex}") from ex

    client = OpenHaspClient(device)
    info(f"Uploading files to device '{device.name}'...")
    changed = await ConfigUploader(config_manager.output_root, client).upload(device, purge, show_diff)
    if changed:
        info(f"Rebooting {device.name} to apply changes")
        await client.reboot()
    else:
        info(f"No changes detected for {device.name}, device is already up-to-date")
    return changed
