import datetime
from datetime import timedelta
from typing import Dict, Any, Optional, Callable, Awaitable

from appdaemon import ADAPI

GLOBAL_TIMER_HANDLES: Dict[str, Any] = {}
APP_SPECIFIC_TIMER_HANDLES: Dict[ADAPI, Dict[str, Any]] = {}


def get_timer_handles_for_app(controller: ADAPI) -> Dict[str, Any]:
    APP_SPECIFIC_TIMER_HANDLES.setdefault(controller, {})
    entry = APP_SPECIFIC_TIMER_HANDLES.get(controller, {})
    return entry


async def schedule_globally(
    controller: ADAPI,
    name: str,
    callback: Callable[[], Awaitable[...]],
    delay: int,
    **kwargs
):
    # controller.log(f"Scheduling '{name}' globally to run in {delay} seconds")
    await cancel(controller, name)

    async def _callback(*args):
        GLOBAL_TIMER_HANDLES.pop(name)
        await callback(*args)

    handle = await controller.run_in(_callback, delay, **kwargs)
    GLOBAL_TIMER_HANDLES[name] = handle
    return handle


async def schedule(
    controller: ADAPI,
    name: str,
    callback: Callable[[Any], Awaitable[None]],
    delay: int,
    **kwargs
):
    # controller.log(f"Scheduling '{name}' for app '{controller.name}' to run in {delay} seconds")
    await cancel(controller, name)

    async def _callback(*args):
        app_handles = get_timer_handles_for_app(controller)
        if name in app_handles.keys():
            app_handles.pop(name)
            APP_SPECIFIC_TIMER_HANDLES[controller] = app_handles
        await callback(*args)

    handle = await controller.run_in(_callback, delay, **kwargs)
    APP_SPECIFIC_TIMER_HANDLES.setdefault(controller, {})
    APP_SPECIFIC_TIMER_HANDLES[controller][name] = handle

    # original_scheduled_time = await get_scheduled_time(controller=controller, name=name)
    # controller.log(f"Scheduled time for timer '{name}' (handle '{handle}') is {original_scheduled_time} (in {delay} seconds from now)")

    return handle


async def get_scheduled_time(controller: ADAPI, name: str) -> Optional[datetime.datetime]:
    """
    Get the planned execution time for a scheduled timer
    :param controller: usually 'self'
    :param name: the name of the timer
    :return: the planned execution time or None if not scheduled
    """
    app_handles = get_timer_handles_for_app(controller)
    existing_timer_handle = app_handles.get(name, None)
    if existing_timer_handle is None:
        return None

    scheduler_entries = await controller.get_scheduler_entries()
    # controller.log(f"Scheduler entries: {scheduler_entries}")
    app_name = controller.name
    if app_name not in scheduler_entries:
        return None
    app_scheduler_entries = scheduler_entries[app_name]
    # controller.log(f"App handles for app '{app_name}' entries: {app_scheduler_entries}")
    if existing_timer_handle not in app_scheduler_entries:
        return None
    timer_entry = app_scheduler_entries[existing_timer_handle]
    planned_execution_time = timer_entry.get("timestamp", None)
    if planned_execution_time:
        parsed_time = datetime.datetime.fromisoformat(planned_execution_time).replace(tzinfo=datetime.timezone.utc)
    else:
        parsed_time = None
    return parsed_time


async def cancel_globally(controller: ADAPI, name: str):
    existing_timer_handle: Optional[str] = GLOBAL_TIMER_HANDLES.get(name, None)
    if existing_timer_handle is not None:
        # controller.log(f"Cancelling '{name}' globally")
        GLOBAL_TIMER_HANDLES.pop(name)
        await controller.cancel_timer(existing_timer_handle)


async def cancel(controller: ADAPI, name: str):
    app_handles = get_timer_handles_for_app(controller)
    existing_timer_handle: Optional[str] = app_handles.get(name, None)
    if existing_timer_handle is not None:
        # controller.log(f"Cancelling '{name}' for app '{controller.name}'")
        app_handles.pop(name)
        await controller.cancel_timer(existing_timer_handle)


async def cancel_all(controller: ADAPI):
    """
    Cancel all timers for the given controller
    :param controller: the controller to cancel timers for
    """
    app_handles = get_timer_handles_for_app(controller)
    for name, handle in app_handles.items():
        if handle is not None:
            await controller.cancel_timer(handle)
    APP_SPECIFIC_TIMER_HANDLES[controller] = {}


def is_scheduled_globally(name: str) -> bool:
    return name in GLOBAL_TIMER_HANDLES.keys()


def is_scheduled(controller: ADAPI, name: str) -> bool:
    app_handles = get_timer_handles_for_app(controller)
    return name in app_handles.keys()


async def run_every(controller: ADAPI, name: str, callback, time_pattern: timedelta):
    async def _scheduled_run_timer_callback(kwargs):
        await callback(entity=None, attribute=None, old=None, new=None, kwargs=None)
        await run_every(controller=controller, name=name, callback=callback, time_pattern=time_pattern)

    await schedule(
        controller=controller,
        name=name,
        callback=_scheduled_run_timer_callback,
        delay=int(time_pattern.total_seconds()),
    )
