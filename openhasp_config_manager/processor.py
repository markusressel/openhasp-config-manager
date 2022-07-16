import json
import re
from pathlib import Path
from typing import List

from openhasp_config_manager.model import Component, WebserverConfig, Device


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

    def _read_webserver_config(self, device_path: Path) -> WebserverConfig | None:
        # TODO: the naming clashes with the "official" config.json of
        #  OpenHasp itself, so we either merge both or rename ours.
        #  Currently I like the idea of merging them, since we can easily add out own section within
        #  the existing structure without breaking other stuff.
        credentials_path = Path(device_path, "config.json")
        if credentials_path.exists() and credentials_path.is_file():
            content = credentials_path.read_text()
            loaded = json.loads(content)
            return WebserverConfig(
                loaded["website"],
                loaded["user"],
                loaded["password"]
            )

    def _analyze(self, cfg_dir_root: Path, output_dir_root: Path) -> List[Device]:
        result: List[Device] = []

        common_components_path = Path(cfg_dir_root, "common")
        common_components = self._read_components(common_components_path, prefix="common")

        devices_path = Path(cfg_dir_root, "devices")
        for device_path in devices_path.iterdir():
            if not device_path.is_dir():
                continue

            device_components = self._analyze_device(device_path)
            webserver = self._read_webserver_config(device_path)
            device_output_dir = Path(output_dir_root, device_path.name)

            device = Device(
                path=device_path,
                name=device_path.name,
                components=common_components + device_components,
                webserver=webserver,
                output_dir=device_output_dir,
            )

            result.append(device)

        return result

    @staticmethod
    def _normalize_jsonl(original_content: str) -> str:
        pattern_to_find_beginning_of_objects = re.compile(r'^(?!\n)\s*(?=\{)', re.RegexFlag.MULTILINE)

        parts = pattern_to_find_beginning_of_objects.split(original_content)
        normalized_parts: List[str] = []
        for part in parts:
            part = part.strip()

            # edge case for first match
            if "}" not in part:
                continue

            # ignore lines starting with "//"
            part = "\n".join([line for line in part.splitlines() if not line.strip().startswith("//")])

            # ignore everything after the last closing bracket
            part = part.rsplit("}", maxsplit=1)[0] + "}"

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

        for component in device.components:
            component_output_file = Path(
                device.output_dir,
                component.name
            )

            self._generate_component_output(component, component_output_file)
