import json
import shutil
from pathlib import Path
from typing import List

from openhasp_config_manager.const import COMMON_FOLDER_NAME, DEVICES_FOLDER_NAME
from openhasp_config_manager.model import Component, Config, Device, OpenhaspConfigManagerConfig, MqttConfig, \
    HttpConfig, GuiConfig, HaspConfig, DeviceConfig, ScreenConfig
from openhasp_config_manager.processing import DeviceProcessor
from openhasp_config_manager.processing.jsonl.jsonl import ObjectDimensionsProcessor
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.ui.util import echo
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
        self._cfg_root = cfg_root
        self._output_root = output_root

        self._variable_manager = variable_manager

    def analyze(self) -> List[Device]:
        """
        Analyze the configuration file tree and the contents of relevant files.
        The result will be a list of Device object instances, representing the structure
        and configuration found.

        :return: list of devices
        """
        echo(f"Analyzing config files in '{self._cfg_root}'...")
        return self._analyze(self._cfg_root, self._output_root)

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
                echo(f"Error reading config '{device_path}': {ex}", color="red")
                raise ex

            device_components = self._analyze_device(device_path)

            device = Device(
                path=device_path,
                name=device_path.name,
                components=common_components + device_components,
                config=config,
                output_dir=device_output_dir,
            )

            result.append(device)

        return result

    def _analyze_device(self, device_cfg_dir_root: Path) -> List[Component]:
        return self._read_components(device_cfg_dir_root)

    @staticmethod
    def _read_components(path: Path, prefix: str = "") -> List[Component]:
        result: List[Component] = []

        for suffix in [".jsonl", ".cmd"]:

            for file in path.rglob(f"*{suffix}"):
                if not file.is_file():
                    continue

                content = file.read_text()

                name_parts = []
                if len(prefix) > 0:
                    name_parts.append(prefix)
                name_parts = name_parts + list(file.relative_to(path).parts)

                name = "_".join(name_parts)
                component = Component(
                    name=name,
                    type=suffix[1:],
                    path=file,
                    content=content,
                )
                result.append(component)

        return result

    def _read_config(self, device_path: Path) -> Config | None:
        config_file = Path(device_path, CONFIG_FILE_NAME)
        if config_file.exists() and config_file.is_file():
            content = config_file.read_text()
            loaded = json.loads(content)

            gui_config = self._parse_gui_config(loaded["gui"])
            screen_rotated = gui_config.rotate % 2 == 1

            config = Config(
                openhasp_config_manager=self._parse_openhasp_config_manager_config(loaded["openhasp_config_manager"],
                                                                                   screen_rotated),
                mqtt=self._parse_mqtt_config(loaded["mqtt"]),
                http=self._parse_http_config(loaded["http"]),
                gui=self._parse_gui_config(loaded["gui"]),
                hasp=self._parse_hasp_config(loaded["hasp"])
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

    def process(self, devices: List[Device] = None) -> List[Device]:
        """
        Process the configuration and generate the corresponding output
        :return:
        """
        if devices is None:
            devices = self.analyze()

        self._generate_output(devices)
        return devices

    def _generate_output(self, devices: List[Device]):
        for device in devices:

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

            # let the processor manage each component
            for component in device.components:
                output_content = device_processor.normalize(device, component)
                try:
                    device_validator.validate(component, output_content)
                except Exception as ex:
                    echo(f"Validation for {component.path} failed: {ex}", color="red")
                    raise ex

                self._write_output(device, component, output_content)

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
