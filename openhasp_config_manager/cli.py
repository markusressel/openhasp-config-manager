from pathlib import Path

import click

PARAM_CFG_DIR = "cfg_dir"
PARAM_OUTPUT_DIR = "output_dir"
PARAM_DEVICE = "device"
PARAM_CMD = "cmd"
PARAM_PAYLOAD = "payload"

CMD_OPTION_NAMES = {
    PARAM_CFG_DIR: ["--config-dir", "-c"],
    PARAM_OUTPUT_DIR: ["--output-dir", "-o"],
    PARAM_DEVICE: ["--device", "-d"],
    PARAM_CMD: ["--command", "-C"],
    PARAM_PAYLOAD: ["--payload", "-p"],
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
    return CMD_OPTION_NAMES[parameter]


@cli.command(name="generate")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=True,
              type=click.Path(exists=True),
              help='Root directory of your config files.')
@click.option(*get_option_names(PARAM_OUTPUT_DIR),
              required=True,
              default=Path("./output"),
              type=click.Path(),
              help='Root directory of where to put the generated output files.')
@click.option(*get_option_names(PARAM_DEVICE), required=False, default=None,
              help='Only generate the output for the specified device.')
def c_generate(config_dir: Path, output_dir: Path, device: str):
    """
    Generates the output files for all devices in the given config directory.

    :param config_dir: Root directory of your config files.
    :param output_dir: Root directory of where to put the generated output files.
    :param device: Only generate the output for the specified device.
    """
    _generate(config_dir, output_dir, device)


def _generate(config_dir: Path, output_dir: Path, device: str):
    from openhasp_config_manager import ConfigProcessor
    processor = ConfigProcessor(config_dir, output_dir)

    devices = processor.analyze()
    if device is not None:
        devices = list(filter(lambda x: x.name == device, devices))

    processor.process(devices)


@cli.command(name="upload")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=True,
              type=click.Path(exists=True),
              help='Root directory of your config files.')
@click.option(*get_option_names(PARAM_OUTPUT_DIR),
              required=True,
              default=Path("./output"),
              type=click.Path(),
              help='Root directory of where the generated output files from the "generate" command are located.')
@click.option(*get_option_names(PARAM_DEVICE), required=False, default=None,
              help='Only upload the generated files for the specified device.')
def c_upload(config_dir: Path, output_dir: Path, device: str):
    """
    Uploads the previously generated configuration to their corresponding devices.

    :param config_dir: Root directory of the config files.
    :param output_dir: Root directory of where the generated output files from the "generate" command are located.
    :param device: name of a single device to process only
    """
    _upload(config_dir, output_dir, device)


def _upload(config_dir: Path, output_dir: Path, device: str):
    from openhasp_config_manager import ConfigProcessor
    from openhasp_config_manager import ConfigUploader

    processor = ConfigProcessor(config_dir, output_dir)

    devices = processor.analyze()
    if device is not None:
        devices = list(filter(lambda x: x.name == device, devices))

    uploader = ConfigUploader(output_dir)
    uploader.upload(devices)


@cli.command(name="deploy")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=True,
              type=click.Path(exists=True),
              help='Root directory of your config files.')
@click.option(*get_option_names(PARAM_OUTPUT_DIR),
              required=True,
              default=Path("./output"),
              type=click.Path(),
              help='Root directory of where to put the generated output files.')
@click.option(*get_option_names(PARAM_DEVICE), required=False, default=None,
              help='Only deploy the specified device.')
def c_deploy(config_dir: Path, output_dir: Path, device: str):
    """
    Combines the generation and upload of a configuration.

    :param config_dir: Root directory of the config files.
    :param output_dir: Root directory of where to put the generated output files.
    :param device: name of a single device to process only
    """
    _deploy(config_dir, output_dir, device)


def _deploy(config_dir: Path, output_dir: Path, device: str):
    _generate(config_dir, output_dir, device)
    _upload(config_dir, output_dir, device)


@cli.command(name="cmd")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=True,
              type=click.Path(exists=True),
              help='Root directory of your config files.')
@click.option(*get_option_names(PARAM_DEVICE),
              required=True,
              help='Device to send the command to.')
@click.option(*get_option_names(PARAM_CMD),
              required=True,
              help='The name of the command.')
@click.option(*get_option_names(PARAM_PAYLOAD),
              required=False,
              default="",
              help='Command payload.')
def c_cmd(config_dir: Path, device: str, command: str, payload: str):
    _cmd(config_dir, device, command, payload)


def _cmd(config_dir: Path, device: str, command: str, payload: str):
    from openhasp_config_manager import ConfigProcessor
    processor = ConfigProcessor(config_dir, "./nonexistent")

    devices = processor.analyze()
    if device is not None:
        devices = list(filter(lambda x: x.name == device, devices))

    from openhasp_config_manager.openhasp import OpenHaspClient
    client = OpenHaspClient()

    for device in devices:
        client.command(device, command, payload)


if __name__ == '__main__':
    cli()