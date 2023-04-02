from pathlib import Path

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.uploader import ConfigUploader

if __name__ == '__main__':
    config_dir = Path("./openhasp-configs")
    output_dir = Path("./output")

    variable_manager = VariableManager(cfg_root=config_dir)
    config_manager = ConfigManager(
        cfg_root=config_dir,
        output_root=output_dir,
        variable_manager=variable_manager
    )

    devices = config_manager.analyze()

    touch_down_1 = next(filter(lambda x: x.name == "touch_down_1", devices))

    client = OpenHaspClient(touch_down_1)
    uploader = ConfigUploader(output_dir, client)

    # deploy the local config to the device
    uploader.upload(device=touch_down_1, purge=False, print_diff=True)

    # update an object on the device (via MQTT)
    client.set_text(
        obj="p1b10",
        text="Hello World!",
    )
