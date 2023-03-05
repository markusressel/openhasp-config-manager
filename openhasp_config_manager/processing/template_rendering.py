import logging
import re
from typing import Dict, List

import jinja2

from openhasp_config_manager.ui.util import echo, error

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)

_j2_env = jinja2.Environment(undefined=jinja2.DebugUndefined)


def render_dict_recursive(
        input: Dict,
        template_vars: Dict,
        result_key_path: List[str] = None,
) -> Dict[str, any]:
    """
    Recursively called function to resolve templates within the given input dict
    :param input: the dict which (possibly) contains templates
    :param template_vars: a map specifying the value of template variables # TODO: this might need context as well... right?
    :param result_key_path:
    :return:
    """
    if result_key_path is None:
        result_key_path = []

    result = {}

    finished = False
    progress = 0
    last_pending = None
    while not finished:
        pending = []
        finished = True
        keys = list(input.keys())
        for key in keys:
            value = input[key]
            # key
            rendered_key = key
            key_undefined = False
            if "{{" in key:
                try:
                    rendered_key = _render_template(key, template_vars)
                    key_undefined = _has_undeclared_variables(rendered_key)
                except Exception as ex:
                    error(f"Undefined key: {key_undefined}, value: {key}")
                    key_undefined = True

            # value
            value_undefined = False
            rendered_value = value
            if isinstance(value, dict) and rendered_key is not None and not key_undefined:
                rendered_value = render_dict_recursive(
                    input=value,
                    template_vars=template_vars,
                    result_key_path=result_key_path + [rendered_key]
                )
            elif isinstance(value, str):
                try:
                    rendered_value = _render_template(value, template_vars)
                    value_undefined = _has_undeclared_variables(rendered_value)
                except Exception as ex:
                    # print(f"Undefined value: {value_undefined}, value: {value}")
                    value_undefined = True

            if key_undefined:
                pending.append(key)
            elif key in pending:
                pending.remove(key)
            if value_undefined:
                pending.append(f"{key}__value")
            elif f"{key}__value" in pending:
                pending.remove(f"{key}__value")

            if key_undefined or value_undefined:
                # still has undefined keys
                # print(f"Undefined keys: {key_undefined}, Undefined values: {value_undefined}")
                finished = False
            else:
                # add it to the template_vars data at the correct location
                # which allows later iterations to render the template correctly
                tmp = template_vars
                for idx, p in enumerate(result_key_path):
                    if p not in tmp.keys():
                        tmp[p] = {}
                    tmp = tmp[p]
                tmp.pop(key, None)
                tmp[rendered_key] = rendered_value

                if rendered_key not in result or result[rendered_key] != rendered_value:
                    progress += 1

                # create the resulting (sub-)dictionary
                result[rendered_key] = rendered_value

                finished = finished and True

        if len(pending) <= 0:
            return result
        elif pending == last_pending:
            echo(f"No progression while rendering templates, unable to render: {pending}")
            return result
        else:
            last_pending = pending

    return result


def _render_template(content: str, template_vars: Dict[str, str]) -> str:
    inner_templates = re.findall(r"\{\{.+\}\}", content[2:-2])
    for inner_template in inner_templates:
        if inner_template != content[2:-2]:
            rendered = _render_template(inner_template, template_vars)
            content = content.replace(inner_template, rendered)
    try:
        template = _j2_env.from_string(content)
        rendered = template.render(template_vars)
        return rendered
    except Exception as ex:
        LOGGER.exception(ex)
        print(f"{ex}: \n\n{content}\n\n {template_vars}")
        raise ex


def _has_undeclared_variables(rendered_value):
    from jinja2.meta import find_undeclared_variables
    ast = _j2_env.parse(rendered_value)
    return find_undeclared_variables(ast)
