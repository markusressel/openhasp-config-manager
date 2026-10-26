import asyncio

from openhasp_config_manager.console import info
from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.uploader import ConfigUploader


async def deploy_device(
    config_manager: ConfigManager, device: Device, purge: bool = False, show_diff: bool = False, restart: bool = False
) -> bool:
    """
    Deploy the files of a device as they are on disk: generate its output, upload what changed and make the plate load it.
    The plate only rebuilds its pages (like after a restart, but faster and without losing the connection) if just pages, commands
    and PNG images changed. Idle timeouts and the like are applied to the running plate. It restarts if its MQTT, HTTP or rotation settings, fonts or
    `.bin` files (can be fonts) changed, since it loads those at startup.
    :param purge: remove files from the plate that are not part of the generated output
    :param show_diff: print a diff for each changed file
    :param restart: restart the plate after any change
    :return: whether anything changed
    """
    info(f"Generating output for '{device.name}'...")
    try:
        await asyncio.to_thread(config_manager.process, device)
    except Exception as ex:
        raise Exception(f"Error generating output for {device.name}: {ex.__class__.__name__} {ex}") from ex

    client = OpenHaspClient(device)
    info(f"Uploading files to device '{device.name}'...")
    result = await ConfigUploader(config_manager.output_root, client).upload_changes(device, purge, show_diff)
    if not result.changed:
        info(f"No changes detected for {device.name}, device is already up-to-date")
    elif restart or result.needs_restart:
        info(f"Rebooting {device.name} to apply changes")
        await client.reboot()
    elif result.files or result.deleted:
        info(f"Reloading the pages of {device.name} to apply changes")
        await client.restore_from_files()
    else:
        info(f"Applied the settings of {device.name} to the running device")
    return result.changed
