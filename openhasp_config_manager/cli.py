from pathlib import Path
from typing import List, Tuple

import click

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.model.device import Device

if __name__ == "__main__":
    import os
    import sys

    parent_dir = os.path.abspath(os.path.join(os.path.abspath(__file__), "..", ".."))
    sys.path.append(parent_dir)

from openhasp_config_manager.processing import VariableManager
from openhasp_config_manager.ui.util import echo, info, error, success, warn

PARAM_CFG_DIR = "cfg_dir"
PARAM_OUTPUT_DIR = "output_dir"
PARAM_DEVICE = "device"
PARAM_PURGE = "purge"
PARAM_SHOW_DIFF = "diff"
PARAM_CMD = "cmd"
PARAM_PAYLOAD = "payload"

DEFAULT_CONFIG_PATH = Path("./openhasp-configs")
DEFAULT_OUTPUT_PATH = Path("./output")

CMD_OPTION_NAMES = {
    PARAM_CFG_DIR: {
        "names": ["--config-dir", "-c"],
        "help": """Root directory which contains all of your openHASP configuration files.""",
    },
    PARAM_OUTPUT_DIR: {
        "names": ["--output-dir", "-o"],
        "help": """Target directory to write generated output files to.""",
    },
    PARAM_DEVICE: {
        "names": ["--device", "-d"],
        "help": """
            The name of the device to target.
            Must be one of the device specific folders within the configuration.
        """
    },
    PARAM_CMD: {
        "names": ["--command", "-C"],
        "help": """Name of the command to execute, see: https://www.openhasp.com/latest/commands/""",
    },
    PARAM_PAYLOAD: {
        "names": ["--payload", "-p"],
        "help": """Command payload.""",
    },
    PARAM_PURGE: {
        "names": ["--purge", "-P"],
        "help": """Whether to cleanup the target device by removing files which are not part of the generated output.""",
    },
    PARAM_SHOW_DIFF: {
        "names": ["--diff", "-D"],
        "help": """Whether to show a diff for files uploaded to the target device.""",
    },
}

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option()
def cli():
    pass


def get_option_names(parameter: str) -> list:
    """
    Returns a list of all valid console parameter names for a given parameter
    :param parameter: the parameter to check
    :return: a list of all valid names to use this parameter
    """
    return CMD_OPTION_NAMES[parameter]["names"]


def get_option_help(parameter: str) -> str:
    """
    Returns the help message for a given parameter
    :param parameter: the parameter to check
    :return: the help message
    """
    return CMD_OPTION_NAMES[parameter]["help"]


@cli.command(name="help")
def c_help():
    """
    Show this message and exit.
    """
    with click.Context(cli) as ctx:
        echo(ctx.get_help())


@cli.command(name="generate")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_OUTPUT_DIR),
              required=True,
              default=DEFAULT_OUTPUT_PATH,
              type=click.Path(path_type=Path),
              help=get_option_help(PARAM_OUTPUT_DIR))
@click.option(*get_option_names(PARAM_DEVICE), required=False, default=None,
              help=get_option_help(PARAM_DEVICE))
def c_generate(config_dir: Path, output_dir: Path, device: str):
    """
    Generates the output files for all devices in the given config directory.
    """
    try:
        config_manager = _create_config_manager(config_dir, output_dir)
        filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)

        if len(filtered_devices) <= 0:
            if device is None:
                raise Exception("No devices found.")
            else:
                raise Exception(f"No device matches the filter: {device}")

        if len(ignored_devices) > 0:
            ignored_devices_names = list(map(lambda x: x.name, ignored_devices))
            warn(f"Skipping devices: {', '.join(ignored_devices_names)}")

        for device in filtered_devices:
            _generate(config_manager, device)

        success("Done!")
    except Exception as ex:
        error(str(ex))


def _generate(config_manager: ConfigManager, device: Device):
    info(f"Generating output for '{device.name}'...")
    try:
        config_manager.process(device)
    except Exception as ex:
        raise Exception(f"Error generating output for {device.name}: {ex}")


@cli.command(name="upload")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_OUTPUT_DIR),
              required=True,
              default=DEFAULT_OUTPUT_PATH,
              type=click.Path(path_type=Path),
              help=get_option_help(PARAM_OUTPUT_DIR))
@click.option(*get_option_names(PARAM_DEVICE), required=False, default=None,
              help=get_option_help(PARAM_DEVICE))
@click.option(*get_option_names(PARAM_PURGE), is_flag=True,
              help=get_option_help(PARAM_PURGE))
@click.option(*get_option_names(PARAM_SHOW_DIFF), is_flag=True,
              help=get_option_help(PARAM_SHOW_DIFF))
def c_upload(config_dir: Path, output_dir: Path, device: str, purge: bool, diff: bool):
    """
    Uploads the previously generated configuration to their corresponding devices.
    """
    try:
        config_manager = _create_config_manager(config_dir, output_dir)
        filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)

        if len(filtered_devices) <= 0:
            if device is None:
                raise Exception("No devices found.")
            else:
                raise Exception(f"No device matches the filter: {device}")

        if len(ignored_devices) > 0:
            ignored_devices_names = list(map(lambda x: x.name, ignored_devices))
            warn(f"Skipping devices: {', '.join(ignored_devices_names)}")

        for device in filtered_devices:
            _upload(device, output_dir, purge, diff)

        success("Done!")
    except Exception as ex:
        error(str(ex))


@cli.command(name="deploy")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_OUTPUT_DIR),
              required=True,
              default=DEFAULT_OUTPUT_PATH,
              type=click.Path(path_type=Path),
              help=get_option_help(PARAM_OUTPUT_DIR))
@click.option(*get_option_names(PARAM_DEVICE), required=False, default=None,
              help=get_option_help(PARAM_DEVICE))
@click.option(*get_option_names(PARAM_PURGE), is_flag=True,
              help=get_option_help(PARAM_PURGE))
@click.option(*get_option_names(PARAM_SHOW_DIFF), is_flag=True,
              help=get_option_help(PARAM_SHOW_DIFF))
def c_deploy(config_dir: Path, output_dir: Path, device: str, purge: bool, diff: bool):
    """
    Combines the generation and upload of a configuration.
    """
    try:
        config_manager = _create_config_manager(config_dir, output_dir)
        filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)

        if len(filtered_devices) <= 0:
            if device is None:
                raise Exception("No devices found.")
            else:
                raise Exception(f"No device matches the filter: {device}")

        if len(ignored_devices) > 0:
            ignored_devices_names = list(map(lambda x: x.name, ignored_devices))
            warn(f"Skipping devices: {', '.join(ignored_devices_names)}")

        for device in filtered_devices:
            _deploy(
                config_manager=config_manager,
                device=device,
                output_dir=output_dir,
                purge=purge,
                show_diff=diff
            )

        success("Done!")
    except Exception as ex:
        error(str(ex))


@cli.command(name="cmd")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_DEVICE),
              required=True,
              help=get_option_help(PARAM_DEVICE))
@click.option(*get_option_names(PARAM_CMD),
              required=True,
              help=get_option_help(PARAM_CMD))
@click.option(*get_option_names(PARAM_PAYLOAD),
              required=False,
              default="",
              help=get_option_help(PARAM_PAYLOAD))
def c_cmd(config_dir: Path, device: str, command: str, payload: str):
    """
    Sends a command request to a device.

    The list of possible commands can be found on the official openHASP
    documentation: https://www.openhasp.com/latest/commands
    """
    try:
        config_manager = _create_config_manager(config_dir, Path("./nonexistent"))
        filtered_devices, ignored_devices = _analyze_and_filter(config_manager=config_manager, device_filter=device)

        if len(filtered_devices) <= 0:
            raise Exception(f"No device matches the filter: {device}")

        for device in filtered_devices:
            _cmd(device, command, payload)
        success("Done!")
    except Exception as ex:
        error(str(ex))


def _upload(device: Device, output_dir: Path, purge: bool, show_diff: bool):
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
    from openhasp_config_manager.uploader import ConfigUploader

    client = OpenHaspClient(device)
    uploader = ConfigUploader(output_dir, client)
    try:
        info(f"Uploading files to device '{device.name}'...")
        uploader.upload(device, purge, show_diff)
    except Exception as ex:
        raise Exception(f"Error uploading files to '{device.name}': {ex}")


def _deploy(config_manager: ConfigManager, device: Device, output_dir: Path, purge: bool, show_diff: bool):
    _generate(config_manager, device)
    _upload(device, output_dir, purge, show_diff)
    # _cmd(config_dir, device="touch_down_1", command="reboot", payload="")
    # _reload(config_dir, device)
    _reboot(device)


def _reload(device: Device):
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    client = OpenHaspClient(device)
    client.command("clearpage", "all")
    client.command("run", "L:/boot.cmd")


def _reboot(device: Device):
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    client = OpenHaspClient(device)
    info(f"Rebooting {device.name}...")
    client.reboot()


def _cmd(device: Device, command: str, payload: str):
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    client = OpenHaspClient(device)
    info(f"Sending command {command} to {device.name}...")
    client.command(command, payload)


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


if __name__ == '__main__':
    cli()
