from pathlib import Path
from typing import Dict

import yaml
from yaml import Loader

from openhasp_config_manager.const import COMMON_FOLDER_NAME, DEVICES_FOLDER_NAME


class VariableManager:
    global_vars = {}
    device_vars = {}

    def __init__(self, cfg_root: Path):
        self.cfg_root = Path(cfg_root)
        self._read()

    def get_vars(self, device: str | None) -> Dict:
        if device is not None:
            return self.device_vars.get(device, {})
        else:
            return self.global_vars

    def _read(self):

        global_var_files = self.cfg_root.rglob(f"{COMMON_FOLDER_NAME}/*.yaml")
        for file in global_var_files:
            data = self._load_var_file(file)
            self.global_vars |= data

        devices_path = Path(self.cfg_root, DEVICES_FOLDER_NAME)
        for device_dir in devices_path.iterdir():
            if not device_dir.is_dir():
                continue

            device_var_files = device_dir.rglob(f"*.yaml")
            for file in device_var_files:
                if not file.is_file():
                    continue

                data = self._load_var_file(file)

                device_name = file.parent.name
                if device_name not in self.device_vars.keys():
                    self.device_vars[device_name] = {}

                self.device_vars[device_name] |= data

    @staticmethod
    def _load_var_file(file: Path):
        content = file.read_text()
        return yaml.load(content, Loader=Loader)
