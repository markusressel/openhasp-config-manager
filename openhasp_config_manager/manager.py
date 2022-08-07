import json
import shutil
from pathlib import Path
from typing import List

from openhasp_config_manager.const import COMMON_FOLDER_NAME, DEVICES_FOLDER_NAME
from openhasp_config_manager.model import Component, Config, Device, OpenhaspConfigManagerConfig, MqttConfig, \
    HttpConfig, GuiConfig, HaspConfig, DeviceConfig, ScreenConfig
from openhasp_config_manager.processing import DeviceProcessor
from openhasp_config_manager.processing.jsonl import JsonlObjectProcessor
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.validation import DeviceValidator, JsonlObjectValidator

CONFIG_FILE_NAME = "config.json"


class ConfigManager:

    def __init__(self, cfg_root: Path, output_root: Path):
        self._cfg_root = cfg_root
        self._output_root = output_root

        self._variable_manager = VariableManager(cfg_root)

    def analyze(self) -> List[Device]:
        """
        Analyze the files in cfg_root
        :return: list of devices
        """
        print(f"Analyzing config files in '{self._cfg_root}'...")
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
                print(f"Error reading config '{device_path}': {ex}")
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

            config = Config(
                openhasp_config_manager=self._parse_openhasp_config_manager_config(loaded["openhasp_config_manager"]),
                mqtt=self._parse_mqtt_config(loaded["mqtt"]),
                http=self._parse_http_config(loaded["http"]),
                gui=self._parse_gui_config(loaded["gui"]),
                hasp=self._parse_hasp_config(loaded["hasp"])
            )

            return config

    @staticmethod
    def _parse_openhasp_config_manager_config(data: dict) -> OpenhaspConfigManagerConfig:
        return OpenhaspConfigManagerConfig(
            device=DeviceConfig(
                ip=data["device"]["ip"],
                screen=ScreenConfig(
                    width=data["device"]["screen"]["width"],
                    height=data["device"]["screen"]["height"]
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

            jsonl_processor = JsonlObjectProcessor()
            device_processor = DeviceProcessor(device, jsonl_processor, self._variable_manager)

            jsonl_validator = JsonlObjectValidator()
            device_validator = DeviceValidator(device.config, jsonl_validator)

            # "fill" the processor with all available data for this device
            for component in device.components:
                if component.type == "jsonl":
                    device_processor.add_jsonl(component)
                else:
                    device_processor.add_other(component)

            # let the processor manage each component
            for component in device.components:
                output_content = device_processor.normalize(component)
                try:
                    device_validator.validate(component, output_content)
                except Exception as ex:
                    print(f"Validation for {component.path} failed: {ex}")
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
