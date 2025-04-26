import asyncio
from pathlib import Path

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.processing.variables import VariableManager


async def main():
    """
    Example to set an image on a device using OpenHaspClient.
    """
    config_dir = Path("./openhasp-configs")
    output_dir = Path("./output")

    variable_manager = VariableManager(cfg_root=config_dir)
    config_manager = ConfigManager(
        cfg_root=config_dir,
        output_root=output_dir,
        variable_manager=variable_manager
    )

    devices = config_manager.analyze()
    device = next(filter(lambda x: x.name == "wt32sc01plus_2", devices))

    client = OpenHaspClient(device)

    home_assistant_camera_snapshot_url = "http://192.168.2.20:8123/api/camera_proxy/camera.x1c_00m09a3c2900999_camera?token=75158c6ceb5ba3af8e3821ddce1d40ca763412786dcdeb246ce55a56222af6b9"
    await client.set_image(
        obj="p3b40",
        image=home_assistant_camera_snapshot_url,
        size=(int(108 / 2), int(192 / 2)),
        listen_host="0.0.0.0",
        listen_port=0,
        access_host="192.168.2.199",
        access_port=0,
    )


if __name__ == '__main__':
    asyncio.run(main())
