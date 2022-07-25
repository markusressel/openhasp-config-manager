import json
import re
from pathlib import Path
from typing import List

from openhasp_config_manager.model import Component, Config, Device, MqttConfig, HttpConfig

COMMON_FOLDER_NAME = "common"
DEVICES_FOLDER_NAME = "devices"

CONFIG_FILE_NAME = "config.json"


class ConfigProcessor:

    def __init__(self, cfg_root: Path, output_root: Path):
        self.cfg_root = cfg_root
        self.output_root = output_root

    def analyze(self) -> List[Device]:
        """
        Analyze the files in cfg_root
        :return: list of devices
        """
        print(f"Analyzing config files in '{self.cfg_root}'...")
        return self._analyze(self.cfg_root, self.output_root)

    def process(self, devices: List[Device] = None) -> List[Device]:
        """
        Process the configuration and generate the corresponding output
        :return:
        """
        if devices is None:
            devices = self.analyze()

        for device in devices:
            self._generate_output(device)
        return devices

    def _analyze_device(self, device_cfg_dir_root: Path) -> List[Component]:
        return self._read_components(device_cfg_dir_root)

    def _read_components(self, path: Path, prefix: str = "") -> List[Component]:
        result: List[Component] = []

        for suffix in [".jsonl", ".cmd"]:

            for file in path.rglob(f"*{suffix}"):
                if not file.is_file():
                    continue

                name_parts = []
                if len(prefix) > 0:
                    name_parts.append(prefix)
                name_parts = name_parts + list(file.relative_to(path).parts)

                name = "_".join(name_parts)
                component = Component(name=name, path=file)
                result.append(component)

        return result

    def _read_config(self, device_path: Path) -> Config | None:
        config_file = Path(device_path, CONFIG_FILE_NAME)
        if config_file.exists() and config_file.is_file():
            content = config_file.read_text()
            loaded = json.loads(content)
            return Config(
                mqtt=MqttConfig(
                    name=loaded["mqtt"]["name"],
                    group=loaded["mqtt"]["group"],
                    host=loaded["mqtt"]["host"],
                    port=loaded["mqtt"]["port"],
                    user=loaded["mqtt"]["user"],
                    password=loaded["mqtt"]["pass"]
                ),
                http=HttpConfig(
                    website=loaded["http"]["website"],
                    port=loaded["http"]["port"],
                    user=loaded["http"]["user"],
                    password=loaded["http"]["pass"],
                )
            )

    def _analyze(self, cfg_dir_root: Path, output_dir_root: Path) -> List[Device]:
        result: List[Device] = []

        common_components_path = Path(cfg_dir_root, COMMON_FOLDER_NAME)
        common_components = self._read_components(common_components_path, prefix="common")

        devices_path = Path(cfg_dir_root, DEVICES_FOLDER_NAME)
        if not devices_path.exists():
            raise RuntimeError(
                f"No '{DEVICES_FOLDER_NAME}' sub-folder found in '{cfg_dir_root}'. Please create it and move your "
                f"device configuration files there.")
        for device_path in devices_path.iterdir():
            if not device_path.is_dir():
                continue

            device_components = self._analyze_device(device_path)
            config = self._read_config(device_path)

            device_output_dir = Path(output_dir_root, device_path.name)

            device = Device(
                path=device_path,
                name=device_path.name,
                components=common_components + device_components,
                config=config,
                output_dir=device_output_dir,
            )

            result.append(device)

        return result

    def _normalize_jsonl(self, original_content: str) -> str:
        parts = self._split_jsonl_objects(original_content)
        normalized_parts: List[str] = []
        for part in parts:
            p = json.dumps(json.loads(part), indent=None)
            normalized_parts.append(p)

        return "\n".join(normalized_parts)

    def _generate_component_output(self, component: Component, component_output_file: Path):
        try:
            original_content = component.path.read_text()
            output_content = original_content
            if "jsonl" in component.path.suffix:
                output_content = self._normalize_jsonl(original_content)
            component_output_file.write_text(output_content)
        except Exception as ex:
            raise Exception(f"Error normalizing file '{component.path}': {ex}")

    def _generate_output(self, device: Device):
        device.output_dir.mkdir(parents=True, exist_ok=True)

        # TODO: keep track of which files were generated and make sure we don't
        #  generate the same file twice

        for component in device.components:
            component_output_file = Path(
                device.output_dir,
                component.name
            )

            self._generate_component_output(component, component_output_file)

    def _split_jsonl_objects(self, original_content: str) -> List[str]:
        pattern_to_find_beginning_of_objects = re.compile(r'^(?!\n)\s*(?=\{)', re.RegexFlag.MULTILINE)
        parts = pattern_to_find_beginning_of_objects.split(original_content)

        result = []
        for part in parts:
            part = part.strip()

            # edge case for first match
            if "}" not in part:
                continue

            # ignore lines starting with "//"
            part = "\n".join([line for line in part.splitlines() if not line.strip().startswith("//")])

            # ignore everything after the last closing bracket
            part = part.rsplit("}", maxsplit=1)[0] + "}"

            result.append(part)

        return result
