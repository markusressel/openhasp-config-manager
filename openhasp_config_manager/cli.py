from pathlib import Path

import click

PARAM_CFG_DIR = "cfg_dir"
PARAM_OUTPUT_DIR = "output_dir"
PARAM_DEVICE = "device"
PARAM_PURGE = "purge"
PARAM_CMD = "cmd"
PARAM_PAYLOAD = "payload"

CMD_OPTION_NAMES = {
    PARAM_CFG_DIR: ["--config-dir", "-c"],
    PARAM_OUTPUT_DIR: ["--output-dir", "-o"],
    PARAM_DEVICE: ["--device", "-d"],
    PARAM_CMD: ["--command", "-C"],
    PARAM_PAYLOAD: ["--payload", "-p"],
    PARAM_PURGE: ["--purge", "-P"]
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
              type=click.Path(exists=True, path_type=Path),
              help='Root directory of your config files.')
@click.option(*get_option_names(PARAM_OUTPUT_DIR),
              required=True,
              default=Path("./output"),
              type=click.Path(path_type=Path),
              help='Root directory of where to put the generated output files.')
@click.option(*get_option_names(PARAM_DEVICE), required=False, default=None,
              help='Only generate the output for the specified device.')
def c_generate(config_dir: Path, output_dir: Path, device: str):
    """
    Generates the output files for all devices in the given config directory.
    """
    _generate(config_dir, output_dir, device)


def _generate(config_dir: Path, output_dir: Path, device: str):
    from openhasp_config_manager.manager import ConfigManager
    processor = ConfigManager(config_dir, output_dir)

    devices = processor.analyze()
    if device is not None:
        devices = list(filter(lambda x: x.name == device, devices))

    processor.process(devices)


@cli.command(name="upload")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=True,
              type=click.Path(exists=True, path_type=Path),
              help='Root directory of your config files.')
@click.option(*get_option_names(PARAM_OUTPUT_DIR),
              required=True,
              default=Path("./output"),
              type=click.Path(path_type=Path),
              help='Root directory of where the generated output files from the "generate" command are located.')
@click.option(*get_option_names(PARAM_DEVICE), required=False, default=None,
              help='Only upload the generated files for the specified device.')
@click.option(*get_option_names(PARAM_PURGE), is_flag=True,
              help='Whether to remove files from the device which are not part of the generated output.')
def c_upload(config_dir: Path, output_dir: Path, device: str, purge: bool):
    """
    Uploads the previously generated configuration to their corresponding devices.
    """
    _upload(config_dir, output_dir, device, purge)


def _upload(config_dir: Path, output_dir: Path, device: str, purge: bool):
    from openhasp_config_manager.manager import ConfigManager
    from openhasp_config_manager.uploader import ConfigUploader

    processor = ConfigManager(config_dir, output_dir)

    devices = processor.analyze()
    if device is not None:
        devices = list(filter(lambda x: x.name == device, devices))

    uploader = ConfigUploader(output_dir)
    for device in devices:
        try:
            print(f"Uploading files to device '{device.name}'...")
            uploader.upload(device, purge)
        except Exception as ex:
            print(f"Error uploading files to '{device.name}': {ex}")


@cli.command(name="deploy")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=True,
              type=click.Path(exists=True, path_type=Path),
              help='Root directory of your config files.')
@click.option(*get_option_names(PARAM_OUTPUT_DIR),
              required=True,
              default=Path("./output"),
              type=click.Path(path_type=Path),
              help='Root directory of where to put the generated output files.')
@click.option(*get_option_names(PARAM_DEVICE), required=False, default=None,
              help='Only deploy the specified device.')
@click.option(*get_option_names(PARAM_PURGE), is_flag=True,
              help='Whether to remove files from the device which are not part of the generated output.')
def c_deploy(config_dir: Path, output_dir: Path, device: str, purge: bool):
    """
    Combines the generation and upload of a configuration.
    """
    _deploy(config_dir, output_dir, device, purge)


def _reboot(config_dir, device: str):
    from openhasp_config_manager.manager import ConfigManager
    processor = ConfigManager(config_dir, Path("./nonexistent"))

    devices = processor.analyze()
    if device is not None:
        devices = list(filter(lambda x: x.name == device, devices))

    from openhasp_config_manager.openhasp import OpenHaspClient
    client = OpenHaspClient()

    for device in devices:
        client.reboot(device)


def _reload(config_dir: Path, device: str):
    from openhasp_config_manager.manager import ConfigManager
    processor = ConfigManager(config_dir, Path("./nonexistent"))

    devices = processor.analyze()
    if device is not None:
        devices = list(filter(lambda x: x.name == device, devices))

    from openhasp_config_manager.openhasp import OpenHaspClient
    client = OpenHaspClient()

    for device in devices:
        client.command(device, "run", "clearpage all")
        client.command(device, "run", "L:/boot.cmd")


def _deploy(config_dir: Path, output_dir: Path, device: str, purge: bool):
    _generate(config_dir, output_dir, device)
    _upload(config_dir, output_dir, device, purge)
    # _cmd(config_dir, device="touch_down_1", command="reboot", payload="")
    # _reload(config_dir, device)
    _reboot(config_dir, device)


@cli.command(name="cmd")
@click.option(*get_option_names(PARAM_CFG_DIR),
              required=True,
              type=click.Path(exists=True, path_type=Path),
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
    """
    Sends a command request to a device.
    """
    _cmd(config_dir, device, command, payload)


def _cmd(config_dir: Path, device: str, command: str, payload: str):
    from openhasp_config_manager.manager import ConfigManager
    processor = ConfigManager(config_dir, Path("./nonexistent"))

    devices = processor.analyze()
    if device is not None:
        devices = list(filter(lambda x: x.name == device, devices))

    from openhasp_config_manager.openhasp import OpenHaspClient
    client = OpenHaspClient()

    import json
    for device in devices:
        if len(payload) > 0:
            payload = json.loads(payload)
        client.command(device, command, payload)


if __name__ == '__main__':
    cli()
