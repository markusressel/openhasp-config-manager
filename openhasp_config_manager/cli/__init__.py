import asyncio
from pathlib import Path

import click

from openhasp_config_manager.cli.cmd import c_cmd
from openhasp_config_manager.cli.deploy import c_deploy
from openhasp_config_manager.cli.generate import c_generate
from openhasp_config_manager.cli.gui import c_gui
from openhasp_config_manager.cli.listen import c_listen
from openhasp_config_manager.cli.logs import c_logs
from openhasp_config_manager.cli.screenshot import c_screenshot
from openhasp_config_manager.cli.shell import c_shell
from openhasp_config_manager.cli.state import c_state
from openhasp_config_manager.cli.upload import c_upload
from openhasp_config_manager.cli.vars import c_vars
from openhasp_config_manager.ui.util import echo

PARAM_CFG_DIR = "cfg_dir"
PARAM_OUTPUT_DIR = "output_dir"
PARAM_DEVICE = "device"
PARAM_PURGE = "purge"
PARAM_SHOW_DIFF = "diff"
PARAM_CMD = "cmd"
PARAM_PAYLOAD = "payload"
PARAM_PATH = "path"
PARAM_OBJECT = "object"
PARAM_STATE = "state"
PARAM_MQTT_PATH = "mqtt_path"

DEFAULT_CONFIG_PATH = Path("./openhasp-configs")
DEFAULT_OUTPUT_PATH = Path("./output")
DEFAULT_SCREENSHOT_OUTPUT_PATH = Path("./")

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
    PARAM_PATH: {
        "names": ["--path", "-p"],
        "help": """The subpath inside the configuration directory"""
    },
    PARAM_OBJECT: {
        "names": ["--object", "-o"],
        "help": """The object identifier, f.ex. p1b15"""
    },
    PARAM_STATE: {
        "names": ["--state", "-s"],
        "help": """The state to set. Can also be a json object to set multiple properties in one go."""
    },
    PARAM_MQTT_PATH: {
        "names": ["--path", "-p"],
        "help": """The MQTT sub-path (hasp/<device>/<path>) to listen to."""
    }
}


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


CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option()
def cli():
    pass


@cli.command(name="help")
def c_help():
    """
    Show this message and exit.
    """
    with click.Context(cli) as ctx:
        echo(ctx.get_help())


@cli.command(name="gui")
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
def generate(config_dir: Path, output_dir: Path):
    """
    Launches the GUI of openhasp-config-manager.
    """
    asyncio.run(
        c_gui(config_dir, output_dir)
    )

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
def generate(config_dir: Path, output_dir: Path, device: str):
    """
    Generates the output files for all devices in the given config directory.
    """
    asyncio.run(
        c_generate(config_dir, output_dir, device)
    )


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
def deploy(config_dir: Path, output_dir: Path, device: str, purge: bool, diff: bool):
    """
    Combines the generation and upload of a configuration.
    """
    asyncio.run(
        c_deploy(config_dir, output_dir, device, purge, diff)
    )


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
def upload(config_dir: Path, output_dir: Path, device: str, purge: bool, diff: bool):
    """
    Uploads the previously generated configuration to their corresponding devices.
    """
    asyncio.run(
        c_upload(config_dir, output_dir, device, purge, diff)
    )


@cli.command(name="logs")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_DEVICE), required=True, default=None,
              help=get_option_help(PARAM_DEVICE))
def logs(config_dir: Path, device: str):
    """
    Prints the logs of a device.
    """
    asyncio.run(
        c_logs(config_dir, device)
    )


@cli.command(name="shell")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_DEVICE), required=True, default=None,
              help=get_option_help(PARAM_DEVICE))
def shell(config_dir: Path, device: str):
    """
    Connects to the telnet server of a device.
    """
    asyncio.run(
        c_shell(config_dir, device)
    )


@cli.command(name="listen")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_DEVICE),
              required=False,
              help=get_option_help(PARAM_DEVICE))
@click.option(*get_option_names(PARAM_MQTT_PATH),
              required=True,
              help=get_option_help(PARAM_MQTT_PATH))
def listen(config_dir: Path, device: str, path: str):
    """
    Sends a state update request to a device.
    """
    asyncio.run(
        c_listen(config_dir, device, path)
    )


@cli.command(name="cmd")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_DEVICE),
              required=False,
              help=get_option_help(PARAM_DEVICE))
@click.option(*get_option_names(PARAM_CMD),
              required=True,
              help=get_option_help(PARAM_CMD))
@click.option(*get_option_names(PARAM_PAYLOAD),
              required=False,
              default="",
              help=get_option_help(PARAM_PAYLOAD))
def cmd(config_dir: Path, device: str, command: str, payload: str):
    """
    Sends a command request to a device.

    The list of possible commands can be found on the official openHASP
    documentation: https://www.openhasp.com/latest/commands
    """
    asyncio.run(
        c_cmd(config_dir, device, command, payload)
    )


@cli.command(name="state")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_DEVICE),
              required=False,
              help=get_option_help(PARAM_DEVICE))
@click.option(*get_option_names(PARAM_OBJECT),
              required=True,
              help=get_option_help(PARAM_OBJECT))
@click.option(*get_option_names(PARAM_STATE),
              required=True,
              help=get_option_help(PARAM_STATE))
def state(config_dir: Path, device: str, object: str, state: str):
    """
    Sends a state update request to a device.
    """
    asyncio.run(
        c_state(config_dir, device, object, state)
    )


@cli.command(name="vars")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_PATH),
              required=False,
              default="",
              help=get_option_help(PARAM_PATH))
def vars(config_dir: Path, path: str):
    """
    Prints the variables accessible in a given path.
    """
    asyncio.run(
        c_vars(config_dir, path)
    )


@cli.command(name="screenshot")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_DEVICE),
              required=True,
              help=get_option_help(PARAM_DEVICE))
@click.option(*get_option_names(PARAM_OUTPUT_DIR),
              required=True,
              default=DEFAULT_SCREENSHOT_OUTPUT_PATH,
              type=click.Path(path_type=Path),
              help=get_option_help(PARAM_OUTPUT_DIR))
def screenshot(config_dir: Path, device: str, output_dir: Path):
    """
    Requests a screenshot from the given device and stores it to the given output directory.
    """
    asyncio.run(
        c_screenshot(config_dir, device, output_dir)
    )
