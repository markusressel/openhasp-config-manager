import asyncio
from pathlib import Path

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.uploader import ConfigUploader


async def event_callback(topic: str, payload: bytes):
    print(f"MQTT Event: {topic} - {payload.decode('utf-8')}")


async def state_callback(topic: str, payload: bytes):
    print(f"State Event: {topic} - {payload.decode('utf-8')}")


async def main():
    config_dir = Path("./openhasp-configs")
    output_dir = Path("./output")

    variable_manager = VariableManager(cfg_root=config_dir)
    config_manager = ConfigManager(
        cfg_root=config_dir,
        output_root=output_dir,
        variable_manager=variable_manager
    )

    devices = config_manager.analyze()

    device = next(filter(lambda x: x.name == "touch_down_1", devices))

    client = OpenHaspClient(device)
    uploader = ConfigUploader(output_dir, client)

    # deploy the local config to the device
    uploader.upload(device=device, purge=False, print_diff=True)

    # subscribe to state changes of object p1b22 (async)
    await client.listen_state(obj="p1b22", callback=state_callback)
    await client.listen_state(obj="p1b29", callback=state_callback)
    # cancel a previously registered callback
    # note: this will effect both previously registered lines
    await client.cancel_callback(callback=state_callback)

    # subscribe to all MQTT events (async)
    await client.listen_event(path="#", callback=event_callback)

    # update an object on the device (via MQTT)
    await client.set_text(
        obj="p1b10",
        text="Hello!",
    )

    await asyncio.sleep(10)

    await client.set_text(
        obj="p1b10",
        text="World!",
    )

    # wait forever (to let "listen_event" and "listen_state" tasks continue)
    await asyncio.Event().wait()


if __name__ == '__main__':
    asyncio.run(main())
