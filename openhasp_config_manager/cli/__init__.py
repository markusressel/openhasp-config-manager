import pathlib
from pathlib import Path

import click

from openhasp_config_manager.cli.cmd import c_cmd
from openhasp_config_manager.cli.deploy import c_deploy
from openhasp_config_manager.cli.generate import c_generate
from openhasp_config_manager.cli.screenshot import c_screenshot
from openhasp_config_manager.cli.upload import c_upload
from openhasp_config_manager.ui.util import echo

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
    c_generate(config_dir, output_dir, device)


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
    c_deploy(config_dir, output_dir, device, purge, diff)


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
    c_upload(config_dir, output_dir, device, purge, diff)


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
def cmd(config_dir: Path, device: str, command: str, payload: str):
    """
    Sends a command request to a device.

    The list of possible commands can be found on the official openHASP
    documentation: https://www.openhasp.com/latest/commands
    """
    c_cmd(config_dir, device, command, payload)


@cli.command(name="screenshot")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=False,
              default=DEFAULT_CONFIG_PATH,
              type=click.Path(exists=True, path_type=Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_DEVICE),
              required=True,
              help=get_option_help(PARAM_DEVICE))
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=True,
              type=click.Path(exists=False, path_type=pathlib.Path),
              help=get_option_help(PARAM_CFG_DIR))
@click.option(*get_option_names(PARAM_OUTPUT_DIR),
              required=True,
              default=DEFAULT_OUTPUT_PATH,
              type=click.Path(path_type=Path),
              help=get_option_help(PARAM_OUTPUT_DIR))
def screenshot(config_dir: Path, device: str, output_dir: Path):
    """
    Requests a screenshot from the given device and stores it to the given output directory.
    """
    c_screenshot(config_dir, device, output_dir)
