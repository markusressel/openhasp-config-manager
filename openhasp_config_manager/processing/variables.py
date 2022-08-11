from pathlib import Path
from typing import Dict

import yaml
from yaml import Loader


class VariableManager:
    path_vars = {}

    def __init__(self, cfg_root: Path):
        self.cfg_root = Path(cfg_root)
        self._read()

    def get_vars(self, path: Path) -> Dict:
        path_vars = self._get_vars_for_path(path)
        return path_vars

    def _get_vars_for_path(self, path: Path):
        result = {}
        relative_paths = path.relative_to(self.cfg_root).parent.parts

        current_path = self.cfg_root.relative_to(self.cfg_root)

        current_path_str = str(current_path)
        result |= self.path_vars.get(current_path_str, {})
        for subfolder in relative_paths:
            current_path = Path(current_path, subfolder)
            current_path_str = str(current_path)
            result |= self.path_vars.get(current_path_str, {})

        return result

    def _read(self):
        for toplevel_path in [self.cfg_root]:
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

                    sub_path = path.relative_to(self.cfg_root)
                    sub_path_str = str(sub_path)
                    if sub_path_str not in self.path_vars.keys():
                        self.path_vars[sub_path_str] = {}
                    self.path_vars[sub_path_str] |= data

    @staticmethod
    def _load_var_file(file: Path):
        content = file.read_text()
        return yaml.load(content, Loader=Loader)
