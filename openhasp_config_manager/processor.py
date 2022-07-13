import json
import re
from pathlib import Path
from typing import List

from openhasp_config_manager.model import Component, Page, WebserverConfig, Device


class ConfigProcessor:

    def __init__(self, cfg_root: Path, output_root: Path):
        self.cfg_root = cfg_root
        self.output_root = output_root

    def process(self) -> List[Device]:
        print(f"Analyzing config files in '{self.cfg_root}'...")
        devices = self._analyze(self.cfg_root, self.output_root)

        self._generate_output(self.cfg_root, self.output_root, devices)
        return devices

    @staticmethod
    def _analyze_component(component_path: Path) -> Component:
        index, name = component_path.name.split("_")

        return Component(
            name=name.removesuffix(".jsonl"),
            index=int(index),
            path=component_path,
        )

    def _analyze_page(self, page_path: Path) -> Page:
        components: List[Component] = []

        for component_file in page_path.glob("*.jsonl"):
            if not component_file.is_file():
                continue

            component = self._analyze_component(component_file)
            components.append(component)

        index, name = page_path.name.split("_")

        return Page(
            name=name,
            index=int(index),
            path=page_path,
            components=components,
        )

    def _analyze_device(self, device_cfg_dir_root: Path) -> List[Page]:
        result: List[Page] = []

        pages_path = Path(device_cfg_dir_root, "pages")
        for page_path in pages_path.iterdir():
            if not page_path.is_dir():
                continue

            page = self._analyze_page(page_path)
            result.append(page)

        return result

    def _read_webserver_config(self, device_path: Path) -> WebserverConfig | None:
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

        # TODO: handle common components
        common_components_path = Path(cfg_dir_root, "common")

        devices_path = Path(cfg_dir_root, "devices")
        for device_path in devices_path.iterdir():
            if not device_path.is_dir():
                continue

            pages = self._analyze_device(device_path)
            webserver = self._read_webserver_config(device_path)
            device_output_dir = Path(output_dir_root, device_path.name)

            device = Device(
                path=device_path,
                name=device_path.name,
                pages=pages,
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
            normalized = self._normalize_jsonl(original_content)
            component_output_file.write_text(normalized)
        except Exception as ex:
            raise Exception(f"Error normalizing file '{component.path}': {ex}")

    def _generate_page_output(self, page: Page, page_output_dir: Path):
        for component in page.components:
            component_output_file = Path(
                page_output_dir,
                f"{page.index}_{page.name}__{component.index}_{component.name}.jsonl"
            )
            page_output_dir.mkdir(parents=True, exist_ok=True)
            self._generate_component_output(component, component_output_file)

    def _generate_device_output(self, device: Device):
        device.output_dir.mkdir(parents=True, exist_ok=True)

        # *.cmd files in device subtree
        for cmd_file in device.path.rglob("*.cmd"):
            original_content = cmd_file.read_text()
            output_file = Path(device.output_dir, cmd_file.name)
            output_file.write_text(original_content)

        # device-specific common files
        common_path = Path(device.path, "common")
        for common_file in common_path.glob("*.jsonl"):
            original_content = common_file.read_text()
            output_file = Path(device.output_dir, common_file.name)
            normalized = self._normalize_jsonl(original_content)
            output_file.write_text(normalized)

        # page-specific files for this device
        for page in device.pages:
            page_output_dir = Path(device.output_dir)
            self._generate_page_output(page, page_output_dir)

    def _generate_output(self, cfg_root_dir: Path, output_root_dir: Path, devices: List[Device]):
        # global common files
        src_common_path = Path(cfg_root_dir, "common")

        output_common_path = Path(output_root_dir, "common")
        output_common_path.mkdir(parents=True, exist_ok=True)

        # TODO: naming clashes between common and device specific files
        #  can still happen and there is no warning about them
        for common_file in src_common_path.glob("*.jsonl"):
            original_content = common_file.read_text()
            normalized = self._normalize_jsonl(original_content)
            output_file = Path(output_common_path, common_file.name)
            output_file.write_text(normalized)

        # Device specific files
        for device in devices:
            print(f"Generating output files for device '{device.name}'...")

            self._generate_device_output(device)
