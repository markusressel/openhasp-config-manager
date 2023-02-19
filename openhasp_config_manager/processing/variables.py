from pathlib import Path
from typing import Dict, Any

import yaml
from yaml import Loader

from openhasp_config_manager.util import contains_nested_dict_key


class VariableManager:
    """
    Used to manage variable definitions found in YAML files inside the configuration
    directory.
    """

    def __init__(self, cfg_root: Path):
        self._cfg_root: Path = Path(cfg_root)
        self._path_vars: Dict[str, Dict] = self._read(cfg_root)

    def add_var(self, key: str, value: any, path: Path = None):
        self.add_vars({key: value}, path)

    def add_vars(self, vars: Dict[str, Any], path: Path = None):
        if path is None:
            path = self._cfg_root
        relative_path = path.relative_to(self._cfg_root)
        if relative_path.is_file():
            relative_path = relative_path.parent
        relative_path_str = str(relative_path)
        current_vars = self._path_vars.get(relative_path_str, {})
        self._path_vars[relative_path_str] |= current_vars | vars

    def get_vars(self, path: Path) -> [str, Any]:
        """
        Returns the variable definitions and values for a given path.

        The resulting map will be a combination of all variables available within each
        of the directories along the given path. Variable definitions found in a lower (longer) path
        will override the ones that might be present higher up the path.

        :param path: the path context to use for variable evaluation
        :return: a map of "variable name" -> "variable value given the path context"
        """
        path_vars = self._get_vars_for_path(path)
        return path_vars

    def _get_vars_for_path(self, path: Path) -> Dict[str, Any]:
        """
        Returns the variable definitions and values for a given path.

        The resulting map will be a combination of all variables available within each
        of the directories along the given path. Variable definitions found in a lower (longer) path
        will override the ones that might be present higher up the path.

        :param path: the path context to use for variable evaluation
        :return: a map of "variable name" -> "variable value given the path context"
        """
        result = {}
        current_path = self._cfg_root.relative_to(self._cfg_root)
        current_path_str = str(current_path)
        result |= self._path_vars.get(current_path_str, {})

        relative_path = path.relative_to(self._cfg_root)
        if relative_path.is_file():
            relative_path = relative_path.parent

        relative_paths = relative_path.parts
        for subfolder in relative_paths:
            current_path = Path(current_path, subfolder)
            current_path_str = str(current_path)
            result |= self._path_vars.get(current_path_str, {})

        return result

    def _read(self, path: Path) -> Dict[str, Dict]:
        """
        Reads all "*.yaml" variable definition files in the given path
        :return: a map of "path -> dict of variables"
        """
        result = {}
        for toplevel_path in [path]:
            for p in toplevel_path.glob('**/**'):
                if not p.is_dir():
                    continue

                if p.name.startswith("."):
                    continue

                path_var_files = p.glob("*.yaml")
                for file in path_var_files:
                    if not file.is_file():
                        continue

                    data = self._load_var_file(file)

                    if data is None:
                        # file is empty
                        continue

                    sub_path = p.relative_to(path)
                    sub_path_str = str(sub_path)
                    if sub_path_str not in result.keys():
                        result[sub_path_str] = {}
                    result[sub_path_str] |= data

        if contains_nested_dict_key(result, "items"):
            # TODO: to avoid this, variables could be accessed by only exposing them
            #  to jinja2 templates via a custom function like f.ex. "vars('my.key.items.a')".
            #  This may be cumbersome to use though...
            raise AssertionError(
                "Variables contain key 'items' which conflics with the built-in function of jinja2. Please choose a different name.")

        return result

    @staticmethod
    def _load_var_file(file: Path) -> Dict:
        content = file.read_text()
        return yaml.load(content, Loader=Loader)
