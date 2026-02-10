import logging
from typing import List, Union

import click

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)


def error(text: str):
    prefix = click.style(" FAIL ", fg="black", bg="red")
    click.echo(f"{prefix} ", nl=False)
    echo(text)


def warn(text: str):
    prefix = click.style(" WARN ", fg="black", bg="yellow")
    click.echo(f"{prefix} ", nl=False)
    echo(text)


def info(text: str):
    prefix = click.style(" INFO ", fg="white", bg=(33, 33, 33))
    click.echo(f"{prefix} ", nl=False)
    echo(text)


def success(text: str):
    prefix = click.style("  OK  ", fg="black", bg="green")
    click.echo(f"{prefix} ", nl=False)
    echo(text)


def echo(text: Union[str, List] = "", fg_color=None, bg_color=None):
    """
    Prints a text to the console
    :param text: the text
    :param fg_color: an optional foreground (text) color
    :param bg_color: an optional background color
    """
    if text is not click.termui and text is not str:
        text = str(text)
    if fg_color:
        text = click.style(text, fg=fg_color, bg=bg_color)
    if len(text) > 0:
        LOGGER.debug(text)
    click.echo(text)


def print_diff_to_console(diff_output):
    for line in diff_output.splitlines():
        if line.startswith("+"):
            echo(line, fg_color="green")
        elif line.startswith("-"):
            echo(line, fg_color="red")
        else:
            echo(line)
