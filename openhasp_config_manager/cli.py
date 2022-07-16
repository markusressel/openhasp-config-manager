from pathlib import Path

import click

PARAM_CFG_DIR = "cfg_dir"
PARAM_OUTPUT_DIR = "output_dir"
PARAM_DEVICE = "device"

CMD_OPTION_NAMES = {
    PARAM_CFG_DIR: ["--config-dir", "-c"],
    PARAM_OUTPUT_DIR: ["--output-dir", "-o"],
    PARAM_DEVICE: ["--device", "-d"]
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
def c_generate(cfg_dir: Path, output_dir: Path, device: str):
    """
    Generates the output files for all devices in the given config directory.

    :param cfg_dir: Root directory of your config files.
    :param output_dir: Root directory of where to put the generated output files.
    :param device: Only generate the output for the specified device.
    """
    from openhasp_config_manager import ConfigProcessor
    processor = ConfigProcessor(cfg_dir, output_dir)

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
def c_upload(cfg_dir: Path, output_dir: Path, device: str):
    """
    Uploads the previously generated configuration to their corresponding devices.

    :param cfg_dir: Root directory of the config files.
    :param output_dir: Root directory of where the generated output files from the "generate" command are located.
    :param device: name of a single device to process only
    """
    from openhasp_config_manager import ConfigProcessor
    from openhasp_config_manager import ConfigUploader

    processor = ConfigProcessor(cfg_dir, output_dir)

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
def c_deploy(cfg_dir: Path, output_dir: Path, device: str):
    """
    Combines the generation and upload of a configuration.

    :param cfg_dir: Root directory of the config files.
    :param output_dir: Root directory of where to put the generated output files.
    :param device: name of a single device to process only
    """
    c_generate(cfg_dir, output_dir, device)
    c_upload(cfg_dir, output_dir, device)


if __name__ == '__main__':
    cli()
