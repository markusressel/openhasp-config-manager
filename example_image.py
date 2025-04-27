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

    home_assistant_camera_snapshot_url = "http://192.168.2.20:8123/api/camera_proxy/camera.x1c_00m09a3c2900999_camera?token=baef380cd0905d90ee0a47b397a6626f4ab1a2e4a087540d99555c2d89ec8783"
    await client.set_image(
        obj="p2b40",
        image=home_assistant_camera_snapshot_url,
        # size=(int(108 / 2), int(192 / 2)),
        size=(108, 192),
        listen_host="0.0.0.0",
        listen_port=20000,
        access_host="192.168.2.199",
        access_port=20000,
    )


if __name__ == '__main__':
    asyncio.run(main())
