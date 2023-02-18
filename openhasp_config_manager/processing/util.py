from typing import Dict, List

import jinja2

from openhasp_config_manager.ui.util import echo


def render_dict_recursively(
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

    from jinja2.meta import find_undeclared_variables
    env = jinja2.Environment(undefined=jinja2.DebugUndefined)

    result = {}

    finished = False
    progress = 0
    pending = []
    last_pending = None
    while not finished:
        finished = True
        keys = list(input.keys())
        for key in keys:
            value = input[key]
            # key
            try:
                template = env.from_string(key)
                rendered_key = template.render(template_vars)
                ast = env.parse(rendered_key)
                key_undefined = find_undeclared_variables(ast)
            except Exception as ex:
                echo(f"Undefined key: {key_undefined}, value: {key}", color="red")
                key_undefined = True

            # value
            value_undefined = False
            rendered_value = value
            if isinstance(value, dict) and not key_undefined:
                rendered_value = render_dict_recursively(
                    value,
                    template_vars,
                    result_key_path + [rendered_key]
                )
            elif isinstance(value, str):
                try:
                    template = env.from_string(value)
                    rendered_value = template.render(template_vars)
                    ast = env.parse(rendered_value)
                    value_undefined = find_undeclared_variables(ast)
                except Exception as ex:
                    # print(f"Undefined value: {value_undefined}, value: {value}")
                    value_undefined = True

            if key_undefined:
                pending.append(key)
            if value_undefined:
                pending.append(f"{key}__value")

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
            # No progression while rendering templates, return as is
            return result
        else:
            last_pending = pending

    return result
