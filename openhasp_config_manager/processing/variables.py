from pathlib import Path
from typing import Dict

import yaml
from yaml import Loader

from openhasp_config_manager.const import COMMON_FOLDER_NAME, DEVICES_FOLDER_NAME


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
        current_path = path.relative_to(self.cfg_root).parent
        while current_path is not None:
            current_path_str = str(current_path)
            result |= self.path_vars.get(current_path_str, {})
            if current_path.parent is None or current_path == current_path.parent:
                break
            else:
                current_path = current_path.parent

        return result

    def _read(self):
        common_path = Path(self.cfg_root, COMMON_FOLDER_NAME)
        devices_path = Path(self.cfg_root, DEVICES_FOLDER_NAME)

        for toplevel_path in [common_path, devices_path]:
            for path in toplevel_path.glob('**/**'):
                if not path.is_dir():
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
