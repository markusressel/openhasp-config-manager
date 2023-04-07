import re
import shutil
from pathlib import Path
from typing import List, Set

import orjson

from openhasp_config_manager.const import COMMON_FOLDER_NAME, DEVICES_FOLDER_NAME, SYSTEM_SCRIPTS
from openhasp_config_manager.openhasp_client.model.component import Component
from openhasp_config_manager.openhasp_client.model.config import Config
from openhasp_config_manager.openhasp_client.model.debug_config import DebugConfig
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.model.device_config import DeviceConfig
from openhasp_config_manager.openhasp_client.model.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.hasp_config import HaspConfig
from openhasp_config_manager.openhasp_client.model.http_config import HttpConfig
from openhasp_config_manager.openhasp_client.model.mqtt_config import MqttConfig
from openhasp_config_manager.openhasp_client.model.openhasp_config_manager_config import OpenhaspConfigManagerConfig
from openhasp_config_manager.openhasp_client.model.screen_config import ScreenConfig
from openhasp_config_manager.openhasp_client.model.telnet_config import TelnetConfig
from openhasp_config_manager.openhasp_client.model.wifi_config import WifiConfig
from openhasp_config_manager.processing.device_processor import DeviceProcessor
from openhasp_config_manager.processing.jsonl.jsonl import ObjectDimensionsProcessor
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.ui.util import warn
from openhasp_config_manager.validation.cmd import CmdFileValidator
from openhasp_config_manager.validation.device_validator import DeviceValidator
from openhasp_config_manager.validation.jsonl import JsonlObjectValidator

CONFIG_FILE_NAME = "config.json"


class ConfigManager:
    """
    This class is used to manage multiple device configurations that may be present
    within a given config directory.
    """

    def __init__(self, cfg_root: Path, output_root: Path, variable_manager: VariableManager):
        self.cfg_root = cfg_root
        self._output_root = output_root

        self._variable_manager = variable_manager

    def analyze(self) -> List[Device]:
        """
        Analyze the configuration file tree and the contents of relevant files.
        The result will be a list of Device object instances, representing the structure
        and configuration found.

        :return: list of devices, which can be used in the ConfigManager.process() method
        """
        return self._analyze(self.cfg_root, self._output_root)

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

            device_output_dir = Path(output_dir_root, device_path.name)
            try:
                config = self._read_config(device_path)
            except Exception as ex:
                raise Exception(f"Error reading config '{device_path}': {ex}")

            device_components = self._analyze_device(config, device_path)

            device = Device(
                path=device_path,
                name=device_path.name,
                components=common_components + device_components,
                config=config,
                output_dir=device_output_dir,
            )

            result.append(device)

        return result

    def _analyze_device(self, config: Config, device_cfg_dir_root: Path) -> List[Component]:
        result = self._read_components(device_cfg_dir_root)
        return result

    @staticmethod
    def _compute_component_path_of_pages_config_value(device_cfg_dir_root: Path, config: Config) -> Path | None:
        sub_path = config.hasp.pages[1:]
        sub_path = sub_path.removeprefix("L:/")
        sub_path = sub_path.removeprefix("/")
        if len(sub_path) <= 0:
            return None
        path = Path(device_cfg_dir_root, sub_path)
        relative_path = path.relative_to(device_cfg_dir_root)
        if path.is_file():
            return relative_path
        else:
            warn(f"Could not find file '{relative_path}' referenced by hasp.pages config property, searched in: {path}")
            return None

    def _read_components(self, path: Path, prefix: str = "") -> List[Component]:
        """
        Recursively reads all components from the given path.
        :param path: the root path to read components from
        :param prefix: a prefix to add to the component name
        :return: list of components
        """
        result: List[Component] = []

        for suffix in [".jsonl", ".cmd"]:
            for file in path.rglob(f"*{suffix}"):
                component = self._create_component_from_path(
                    device_cfg_dir_root=path,
                    path=Path(path, file.relative_to(path)).relative_to(path),
                    prefix=prefix
                )
                if component is not None:
                    result.append(component)

        return result

    @staticmethod
    def _create_component_from_path(device_cfg_dir_root: Path, path: Path, prefix: str) -> Component or None:
        file = Path(device_cfg_dir_root, path)

        if not file.is_file():
            warn(f"Not a file, skipping: {file}")
            return None

        content = file.read_text()

        name_parts = []
        if len(prefix) > 0:
            name_parts.append(prefix)
        name_parts = name_parts + list(file.relative_to(device_cfg_dir_root).parts)

        name = "_".join(name_parts)
        suffix = file.suffix
        component = Component(
            name=name,
            type=suffix[1:],
            path=file,
            content=content,
        )
        return component

    def _read_config(self, device_path: Path) -> Config | None:
        config_file = Path(device_path, CONFIG_FILE_NAME)
        if config_file.exists() and config_file.is_file():
            content = config_file.read_text()
            loaded = orjson.loads(content)

            gui_config = self._parse_gui_config(loaded["gui"])
            is_screen_rotated = gui_config.rotate % 2 == 1

            config = Config(
                openhasp_config_manager=self._parse_openhasp_config_manager_config(
                    data=loaded["openhasp_config_manager"],
                    swap_width_and_height=is_screen_rotated
                ),
                wifi=self._parse_wifi_config(loaded["wifi"]),
                mqtt=self._parse_mqtt_config(loaded["mqtt"]),
                http=self._parse_http_config(loaded["http"]),
                gui=self._parse_gui_config(loaded["gui"]),
                hasp=self._parse_hasp_config(loaded["hasp"]),
                debug=self._parse_debug_config(loaded["debug"]),
                telnet=self._parse_telnet_config(loaded["telnet"])
            )

            return config

    @staticmethod
    def _parse_openhasp_config_manager_config(data: dict, swap_width_and_height: bool) -> OpenhaspConfigManagerConfig:
        screen_width_key = "width"
        screen_height_key = "height"

        if swap_width_and_height:
            # swap width and height if screen is rotated
            t = screen_width_key
            screen_width_key = screen_height_key
            screen_height_key = t

        return OpenhaspConfigManagerConfig(
            device=DeviceConfig(
                ip=data["device"]["ip"],
                screen=ScreenConfig(
                    width=data["device"]["screen"][screen_width_key],
                    height=data["device"]["screen"][screen_height_key]
                )
            )
        )

    @staticmethod
    def _parse_wifi_config(data: dict) -> WifiConfig:
        return WifiConfig(
            ssid=data["ssid"],
            password=data["pass"],
        )

    @staticmethod
    def _parse_mqtt_config(data: dict) -> MqttConfig:
        return MqttConfig(
            name=data["name"],
            group=data["group"],
            host=data["host"],
            port=data["port"],
            user=data["user"],
            password=data["pass"],
        )

    @staticmethod
    def _parse_http_config(data: dict) -> HttpConfig:
        return HttpConfig(
            port=data["port"],
            user=data["user"],
            password=data["pass"],
        )

    @staticmethod
    def _parse_gui_config(data: dict) -> GuiConfig:
        return GuiConfig(
            idle1=data["idle1"],
            idle2=data["idle2"],
            bckl=data["bckl"],
            bcklinv=data["bcklinv"],
            rotate=data["rotate"],
            cursor=data["cursor"],
            invert=data["invert"],
            calibration=data["calibration"],
        )

    @staticmethod
    def _parse_hasp_config(data: dict) -> HaspConfig:
        return HaspConfig(
            startpage=data["startpage"],
            startdim=data["startdim"],
            theme=data["theme"],
            color1=data["color1"],
            color2=data["color2"],
            font=data["font"],
            pages=data["pages"],
        )

    @staticmethod
    def _parse_debug_config(data: dict) -> DebugConfig:
        return DebugConfig(
            ansi=data["ansi"],
            baud=data["baud"],
            tele=data["tele"],
            host=data["host"],
            port=data["port"],
            proto=data["proto"],
            log=data["log"],
        )

    @staticmethod
    def _parse_telnet_config(data: dict) -> TelnetConfig:
        return TelnetConfig(
            enable=data["enable"],
            port=data["port"],
        )

    def process(self, device: Device):
        """
        Process the configuration and generate the corresponding output
        """
        self._generate_output(device)

    def _generate_output(self, device: Device):
        self._clear_output(device)

        jsonl_processors = [
            ObjectDimensionsProcessor()
        ]
        device_processor = DeviceProcessor(device, jsonl_processors, self._variable_manager)

        jsonl_validator = JsonlObjectValidator()
        cmd_file_validator = CmdFileValidator()
        device_validator = DeviceValidator(device.config, jsonl_validator, cmd_file_validator)

        # feed device specific data to the processor
        # Note: this also includes common components
        for component in device.components:
            if component.type == "jsonl":
                device_processor.add_jsonl(component)
            else:
                device_processor.add_other(component)

        # only include files which are referenced in a cmd file
        relevant_components = self.find_relevant_components(device)

        # let the processor manage each component
        for component in relevant_components:
            output_content = None
            try:
                output_content = device_processor.normalize(device, component)
            except Exception as ex:
                raise Exception(f"Error normalizing {component.path}: {ex}")

            try:
                device_validator.validate(component, output_content)
            except Exception as ex:
                raise Exception(f"Validation for {component.path} failed: {ex}")

            self._write_output(device, component, output_content)

    def find_relevant_components(self, device: Device) -> List[Component]:
        cmd_components = list(filter(lambda x: x.type == "cmd", device.components))
        jsonl_components = list(filter(lambda x: x.type == "jsonl", device.components))

        referenced_cmd_components = self._find_referenced_cmd_components(cmd_components)

        # find jsonl files referenced in CMD files
        referenced_jsonl_components = self._find_referenced_jsonl_components(cmd_components, jsonl_components)

        # compute component for jsonl file referenced in config.hasp.pages
        pages_jsonl_component_path = self._compute_component_path_of_pages_config_value(device.path, device.config)
        if pages_jsonl_component_path is not None:
            pages_jsonl_component = self._create_component_from_path(
                device_cfg_dir_root=device.path,
                path=pages_jsonl_component_path, prefix=""
            )
            referenced_jsonl_components.add(pages_jsonl_component)

        return list(referenced_jsonl_components) + list(referenced_cmd_components)

    def _find_referenced_cmd_components(self, components: List[Component]) -> Set[Component]:
        result = set()

        system_components = list(filter(lambda x: x.name in SYSTEM_SCRIPTS, components))
        cmd_components = [c for c in components if c.type == "cmd"] + system_components

        # TODO: this should also consider the hierarchy, if a cmd component is not a system component, and
        #  it is also not referenced anywhere, the component is not relevant

        for component in cmd_components:
            cmd_references = self._find_cmd_references_in_cmd_component(component)
            for match in cmd_references:
                matching_components = list(filter(lambda x: x.name == match, components))
                if len(matching_components) <= 0:
                    found_component_names = ','.join([c.name for c in cmd_components])
                    raise AssertionError(
                        f"Referenced CMD component not found: {match}, only found: {found_component_names}")
                result.update(matching_components)

        # system components should always be included
        result.update(system_components)

        return result

    def _find_referenced_jsonl_components(
            self,
            cmd_components: List[Component],
            jsonl_components: List[Component]
    ) -> Set[Component]:
        referenced_jsonl_components = set()
        for component in cmd_components:
            jsonl_references = self._find_jsonl_references_in_cmd_component(component)
            for match in jsonl_references:
                matching_components = list(filter(lambda x: x.name == match, jsonl_components))
                if len(matching_components) <= 0:
                    found_component_names = ','.join([c.name for c in jsonl_components])
                    raise AssertionError(
                        f"Referenced JSONL component not found: {match}, only found: {found_component_names}")
                referenced_jsonl_components.update(matching_components)

        return referenced_jsonl_components

    @staticmethod
    def _find_cmd_references_in_cmd_component(component: Component) -> Set[str]:
        result = set()
        pattern = re.compile("L:/(.*\.cmd)")
        for line in component.content.splitlines():
            matches = re.findall(pattern, line)
            result.update(matches)
        return result

    @staticmethod
    def _find_jsonl_references_in_cmd_component(component: Component) -> Set[str]:
        result = set()
        pattern = re.compile("L:/(.*\.jsonl)")
        for line in component.content.splitlines():
            matches = re.findall(pattern, line)
            result.update(matches)
        return result

    @staticmethod
    def _write_output(device: Device, component: Component, output_content: str):
        device.output_dir.mkdir(parents=True, exist_ok=True)

        component_output_file = Path(
            device.output_dir,
            component.name
        )

        component_output_file.write_text(output_content)

    @staticmethod
    def _clear_output(device: Device):
        if device.output_dir.exists():
            shutil.rmtree(device.output_dir)
