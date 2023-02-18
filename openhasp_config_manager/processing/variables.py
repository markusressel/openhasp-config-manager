from pathlib import Path
from typing import Dict

import yaml
from yaml import Loader


class VariableManager:
    """
    Used to manage variable definitions found in YAML files inside the configuration
    directory.

    Variable values are resolved by inversely traversing the file path (from bottom to top).
    The first variable definition found will be used.
    """
    _path_vars = {}

    def __init__(self, cfg_root: Path):
        self._cfg_root = Path(cfg_root)
        self._read()

    def get_vars(self, path: Path) -> Dict:
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

    def _get_vars_for_path(self, path: Path):
        result = {}
        relative_paths = path.relative_to(self._cfg_root).parent.parts

        current_path = self._cfg_root.relative_to(self._cfg_root)

        current_path_str = str(current_path)
        result |= self._path_vars.get(current_path_str, {})
        for subfolder in relative_paths:
            current_path = Path(current_path, subfolder)
            current_path_str = str(current_path)
            result |= self._path_vars.get(current_path_str, {})

        return result

    def _read(self):
        for toplevel_path in [self._cfg_root]:
            for path in toplevel_path.glob('**/**'):
                if not path.is_dir():
                    continue

                if path.name.startswith("."):
                    continue

                path_var_files = path.glob("*.yaml")
                for file in path_var_files:
                    if not file.is_file():
                        continue

                    data = self._load_var_file(file)

                    sub_path = path.relative_to(self._cfg_root)
                    sub_path_str = str(sub_path)
                    if sub_path_str not in self._path_vars.keys():
                        self._path_vars[sub_path_str] = {}
                    self._path_vars[sub_path_str] |= data

    @staticmethod
    def _load_var_file(file: Path) -> Dict:
        content = file.read_text()
        return yaml.load(content, Loader=Loader)
