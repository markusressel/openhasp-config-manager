from pathlib import Path

import click

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
        _generate(config_dir, output_dir, device)
        success("Done!")
    except Exception as ex:
        error(str(ex))


def _generate(config_dir: Path, output_dir: Path, device: str):
    from openhasp_config_manager.manager import ConfigManager

    variable_manager = VariableManager(cfg_root=config_dir)
    config_manager = ConfigManager(
        cfg_root=config_dir,
        output_root=output_dir,
        variable_manager=variable_manager
    )

    info(f"Analyzing files in '{config_dir}'...")
    devices = config_manager.analyze()
    devices = list(sorted(devices, key=lambda x: x.name))
    device_names = list(map(lambda x: x.name, devices))
    info(f"Found devices: {', '.join(device_names)}")

    filtered_devices = []
    ignored_devices = []
    if device is not None:
        filtered_devices = list(filter(lambda x: x.name == device, devices))
        ignored_devices = list(filter(lambda x: x not in filtered_devices, devices))
    else:
        filtered_devices = devices

    if len(devices) <= 0:
        error("No devices found.")
        return

    if len(filtered_devices) <= 0:
        error(f"No device matches the filter: {device}")
        return

    if len(ignored_devices) > 0:
        ignored_devices_names = list(map(lambda x: x.name, ignored_devices))
        warn(f"Skipping devices: {', '.join(ignored_devices_names)}")

    for device in devices:
        info(f"Generating output for '{device.name}'...")
        config_manager.process(device)


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
        _upload(config_dir, output_dir, device, purge, diff)
        success("Done!")
    except Exception as ex:
        error(str(ex))


def _upload(config_dir: Path, output_dir: Path, device: str, purge: bool, show_diff: bool):
    from openhasp_config_manager.manager import ConfigManager
    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
    from openhasp_config_manager.uploader import ConfigUploader

    variable_manager = VariableManager(cfg_root=config_dir)
    config_manager = ConfigManager(
        cfg_root=config_dir,
        output_root=output_dir,
        variable_manager=variable_manager
    )

    info(f"Analyzing files in '{config_dir}'...")
    devices = config_manager.analyze()
    devices = list(sorted(devices, key=lambda x: x.name))
    device_names = list(map(lambda x: x.name, devices))
    info(f"Found devices: {', '.join(device_names)}")

    filtered_devices = []
    ignored_devices = []
    if device is not None:
        filtered_devices = list(filter(lambda x: x.name == device, devices))
        ignored_devices = list(filter(lambda x: x not in filtered_devices, devices))
    else:
        filtered_devices = devices

    if len(devices) <= 0:
        error("No devices found.")
        return

    if len(filtered_devices) <= 0:
        error(f"No device matches the filter: {device}")
        return

    if len(ignored_devices) > 0:
        ignored_devices_names = list(map(lambda x: x.name, ignored_devices))
        warn(f"Skipping devices: {', '.join(ignored_devices_names)}")

    for device in filtered_devices:
        client = OpenHaspClient(device)
        uploader = ConfigUploader(output_dir, client)
        try:
            info(f"Uploading files to device '{device.name}'...")
            uploader.upload(device, purge, show_diff)
        except Exception as ex:
            error(f"Error uploading files to '{device.name}': {ex}")


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
        _deploy(config_dir, output_dir, device, purge, diff)
        success("Done!")
    except Exception as ex:
        error(str(ex))


def _reboot(config_dir, device: str):
    from openhasp_config_manager.manager import ConfigManager
    variable_manager = VariableManager(cfg_root=config_dir)
    config_manager = ConfigManager(
        cfg_root=config_dir,
        output_root=Path("./nonexistent"),
        variable_manager=variable_manager
    )

    info(f"Analyzing files in '{config_dir}'...")
    devices = config_manager.analyze()
    devices = list(sorted(devices, key=lambda x: x.name))
    device_names = list(map(lambda x: x.name, devices))
    info(f"Found devices: {', '.join(device_names)}")

    filtered_devices = []
    if device is not None:
        filtered_devices = list(filter(lambda x: x.name == device, devices))
    else:
        filtered_devices = devices

    if len(devices) <= 0:
        error("No devices found.")
        return

    if len(filtered_devices) <= 0:
        error(f"No device matches the filter: {device}")
        return

    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    for device in devices:
        client = OpenHaspClient(device)
        info(f"Rebooting {device.name}...")
        client.reboot()


def _reload(config_dir: Path, device: str):
    from openhasp_config_manager.manager import ConfigManager
    variable_manager = VariableManager(cfg_root=config_dir)
    processor = ConfigManager(
        cfg_root=config_dir,
        output_root=Path("./nonexistent"),
        variable_manager=variable_manager
    )

    devices = processor.analyze()
    if device is not None:
        devices = list(filter(lambda x: x.name == device, devices))

    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    for device in devices:
        client = OpenHaspClient(device)
        client.command("clearpage", "all")
        client.command("run", "L:/boot.cmd")


def _deploy(config_dir: Path, output_dir: Path, device: str, purge: bool, show_diff: bool):
    _generate(config_dir, output_dir, device)
    _upload(config_dir, output_dir, device, purge, show_diff)
    # _cmd(config_dir, device="touch_down_1", command="reboot", payload="")
    # _reload(config_dir, device)
    _reboot(config_dir, device)


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
        _cmd(config_dir, device, command, payload)
        success("Done!")
    except Exception as ex:
        error(str(ex))


def _cmd(config_dir: Path, device: str, command: str, payload: str):
    from openhasp_config_manager.manager import ConfigManager
    variable_manager = VariableManager(cfg_root=config_dir)
    config_manager = ConfigManager(
        cfg_root=config_dir,
        output_root=Path("./nonexistent"),
        variable_manager=variable_manager
    )

    info(f"Analyzing files in '{config_dir}'...")
    devices = config_manager.analyze()
    devices = list(sorted(devices, key=lambda x: x.name))
    device_names = list(map(lambda x: x.name, devices))
    info(f"Found devices: {', '.join(device_names)}")

    filtered_devices = []
    if device is not None:
        filtered_devices = list(filter(lambda x: x.name == device, devices))
    else:
        filtered_devices = devices

    if len(devices) <= 0:
        error("No devices found.")
        return

    if len(filtered_devices) <= 0:
        error(f"No device matches the filter: {device}")
        return

    from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient

    for device in devices:
        client = OpenHaspClient(device)
        info(f"Sending command {command} to {device.name}...")
        client.command(command, payload)


if __name__ == '__main__':
    cli()
