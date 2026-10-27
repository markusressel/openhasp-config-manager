"""The values of the templates and variables in a line of text, for the hover card and the values shown next to the text. Qt-free."""

from typing import Any, Callable, List, Optional

from jinja2 import TemplateError

from openhasp_config_manager.gui.domain.colors import Argb, parse_color
from openhasp_config_manager.gui.domain.source.docs import PropertyHelp
from openhasp_config_manager.gui.domain.source.syntax import Language, TokenKind, find_templates, tokenize_line
from openhasp_config_manager.gui.domain.variables.references import part_at

# how much of a value is shown
MAX_LENGTH = 200
_MAX_ITEMS = 8

# the value of a variable in a component of the draft: raises KeyError if it has none
VariableValue = Callable[[str], Any]
# renders a text with templates: None if there is no draft to render with, raises jinja2.TemplateError if it can't be
RenderText = Callable[[str], Optional[str]]


def describe_value(value: Any) -> str:
    """:return: a value as text: scalars as they are written into the files, mappings by their keys, lists by their first items"""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, dict):
        keys = [str(key) for key in value][:_MAX_ITEMS]
        text = "{" + ", ".join(keys) + (", …" if len(value) > _MAX_ITEMS else "") + "}"
    elif isinstance(value, (list, tuple)):
        items = [describe_value(item) for item in value[:_MAX_ITEMS]]
        text = "[" + ", ".join(items) + (", …" if len(value) > _MAX_ITEMS else "") + "]"
    elif value is None:
        text = "none"
    else:
        text = str(value)
    return text if len(text) <= MAX_LENGTH else text[: MAX_LENGTH - 1] + "…"


def variable_help(line: str, column: int, variable_value: VariableValue, render_text: RenderText) -> Optional[PropertyHelp]:
    """
    :return: what the card of the hover shows for a column of a line: the value of the variable there, and what its template
        renders to. None if the column is in no template.
    """
    template = next((token for token in find_templates(line) if token.start <= column < token.end), None)
    if template is None or line.startswith("{#", template.start):
        return None
    text = line[template.start : template.end]
    part = part_at(line, column)
    value = None
    if part is not None:
        try:
            value = describe_value(variable_value(part.name))
        except KeyError:
            pass
    rendered = error = None
    try:
        result = render_text(text)
        rendered = None if result is None else describe_value(result)
    except TemplateError as ex:
        error = str(ex.message)

    name = part.name if value is not None else text
    details = []
    if rendered is not None and (value is None or text.replace(" ", "") != "{{" + name + "}}"):
        details.append(("Renders to", f"`{rendered.replace('`', chr(39))}`"))
    if error is not None:
        details.append(("Can't render", error))
    summary = f"`{value.replace('`', chr(39))}`" if value is not None else "Not a variable with a value."
    return PropertyHelp(name=name, summary=summary, kind="variable" if value is not None else "template", details=details)


def line_values(line: str, render_text: RenderText) -> List[str]:
    """:return: what the templates of a line (not the statements and comments) render to, in order; unusable ones are left out"""
    result = []
    for template in find_templates(line):
        text = line[template.start : template.end]
        if not text.startswith("{{"):
            continue
        try:
            rendered = render_text(text)
        except TemplateError:
            continue
        if rendered is not None:
            result.append(describe_value(rendered))
    return result


def line_colors(line: str, language: Language, render_text: Optional[RenderText]) -> List[Argb]:
    """:return: the colors of a line in order: the color strings, and the templates that render to a color"""
    found = [
        (token.start, parse_color(line[token.start + 1 : token.end - 1]))
        for token in tokenize_line(line, language)
        if token.kind == TokenKind.COLOR
    ]
    if render_text is not None and "{{" in line:
        for template in find_templates(line):
            text = line[template.start : template.end]
            if not text.startswith("{{"):
                continue
            try:
                rendered = render_text(text)
            except TemplateError:
                continue
            if rendered is not None and (color := parse_color(rendered.strip())) is not None:
                found.append((template.start, color))
    return [color for _, color in sorted(found, key=lambda item: item[0]) if color is not None]
