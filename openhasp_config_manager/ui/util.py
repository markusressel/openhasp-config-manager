import logging

import click

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)


def echo(text: str = "", color=None):
    """
    Prints a text to the console
    :param text: the text
    :param color: an optional color
    """
    if text is not click.termui and text is not str:
        text = str(text)
    if color:
        text = click.style(text, fg=color)
    if len(text) > 0:
        LOGGER.debug(text)
    click.echo(text)


def print_diff_to_console(diff_output):
    for line in diff_output.splitlines():
        if line.startswith("+"):
            echo(line, color="green")
        elif line.startswith("-"):
            echo(line, color="red")
        else:
            echo(line)
