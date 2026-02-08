import asyncio
import json
from asyncio import Task
from typing import Callable, Any, List, Awaitable, Dict

import appdaemon.plugins.hass.hassapi as hass

from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient


async def listen_event(
    controller: hass.Hass,
    client: OpenHaspClient,
    path: str,
    callback: Callable[[str, bytes], Awaitable[Any]],
) -> Task:
    """
    Listen to OpenHASP MQTT events
    :param controller: usually 'self'
    :param client: OpenHASP client
    :param callback: callback to call when an event is received
    :param path: mqtt path to listen for
    :return: A handle that can be used to cancel the callback.
    """
    controller.log(f"Listening for '{path}' events")

    async def _callback(topic: str, payload: bytes):
        controller.log(f"Received event on '{topic}': {payload}")
        await callback(topic, payload)

    await client.listen_event(path, _callback)

    # make sure the mqtt subscription is cancelled when the app is stopped or reloaded
    # by registering a custom task that waits indefinitely, until the
    # task is cancelled by AppDaemon
    async def cancel_subscription_task_fun():
        try:
            # wait indefinitely, until the task is cancelled by the caller
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await client.cancel_callback(callback=_callback)

    return await controller.create_task(cancel_subscription_task_fun())


async def listen_state(
    controller: hass.Hass,
    client: OpenHaspClient,
    obj: str,
    callback: Callable[[str, Dict], Awaitable[Any]],
) -> Task:
    """
    Listen to OpenHASP state events
    :param controller: usually 'self'
    :param client: OpenHASP client
    :param obj: object id to listen for (f.ex. p1b10)
    :param callback: callback to call when a matching event is received
    :return: A handle that can be used to cancel the callback.
    """
    controller.log(f"Listening for '{obj}' state changes")

    async def _callback(event_topic: str, event_payload: bytes):
        controller.log(f"Received state change on '{event_topic}': {event_payload}")
        parsed_payload = json.loads(event_payload)
        await callback(event_topic, parsed_payload)

    await client.listen_state(obj=obj, callback=_callback)

    # make sure the mqtt subscription is cancelled when the app is stopped or reloaded
    # by registering a custom task that waits indefinitely, until the
    # task is cancelled by AppDaemon
    async def cancel_subscription_task_fun():
        try:
            # wait indefinitely, until the task is cancelled by the caller
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await client.cancel_callback(callback=_callback)

    return await controller.create_task(cancel_subscription_task_fun())


async def config(
    controller: hass.Hass,
    plate: str,
    submodule: str,
    params: str | List[Any] | Dict[str, Any],
) -> Any:
    """
    Sets the configuration of a submodule on a plate
    :param controller: usually 'self'
    :param plate: name of the plate
    :param submodule: the name of the configuration submodule, f.ex. "gui"
    :param params: parameters to set within the configuration submodule
    :return: Result of the `call_service` function if any
    """
    payload = params
    if isinstance(payload, list):
        payload = " ".join(params)
    elif isinstance(payload, dict):
        payload = json.dumps(payload)
    return await controller.call_service(
        "mqtt/publish",
        topic=f"hasp/{plate}/config/{submodule}",
        payload=payload,
    )
