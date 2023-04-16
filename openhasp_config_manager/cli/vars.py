from pathlib import Path
from typing import Dict, List

from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.ui.util import error, echo


async def _format_variables(variables: Dict) -> str:
    def get_dict_contents(d: Dict, parent_key: str = '', result: List[str] = []):
        for k in sorted(d.keys()):
            v = d[k]
            if isinstance(v, dict):
                get_dict_contents(v, parent_key + k + '.', result)
            elif isinstance(v, list):
                for i in range(len(v)):
                    if isinstance(v[i], dict):
                        get_dict_contents(v[i], parent_key + k + '.' + str(i) + '.', result)
                    else:
                        result.append(f"{parent_key}{k}[{i}]: {v[i]}")
            else:
                result.append(f"{parent_key}{k}: {v}")
        return result

    return "\n".join(get_dict_contents(variables))


async def c_vars(config_dir: Path, path: str):
    try:
        variable_manager = VariableManager(cfg_root=config_dir)
        variable_manager.read()
        variables = variable_manager.get_vars(Path(config_dir, path))
        formatted = await _format_variables(variables)
        echo(formatted)
    except Exception as ex:
        error(str(ex))
