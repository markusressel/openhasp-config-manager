import uuid
from datetime import timedelta, datetime
from typing import Union, List, Set, Any, Optional

from appdaemon import ADAPI
from util import util_common, util_timer

STATE_UNAVAILABLE = "unavailable"
STATE_UNKNOWN = "unknown"


async def listen_state_and_call_immediately(
    controller: ADAPI,
    callback,
    entity_id: Union[str, List[str]],
    debounce_delay: timedelta = timedelta(seconds=0),
    debounce_delay_excluded_states: Set[str] = (),
    throttle_delay: timedelta = timedelta(seconds=0),
    **kwargs: Any
):
    """
    Listens to the state of an entity and calls the callback immediately with the current state.

    :param controller: the appdaemon controller to use for listening to state changes
    :param callback: the callback function to call
    :param entity_id: the entity id or list of entity ids to listen to
    :param debounce_delay: the delay before calling the callback, will be reset if the state changes again
    :param debounce_delay_excluded_states: states that will not trigger the debounce delay
    :param throttle_delay: the minimum time between calls to the callback, regardless of state changes
    :param kwargs: additional arguments to pass to the callback
    """
    timer_key = str(uuid.uuid4())
    last_called_time: Optional[datetime] = None

    async def _callback_wrapper(inner_kwargs):
        """
        Wraps the callback to be called after the debounce delay.
        :param inner_kwargs: the original arguments for the callback
        """
        await callback(
            inner_kwargs["entity_id"],
            inner_kwargs["attribute"],
            inner_kwargs["old"],
            inner_kwargs["new"],
            inner_kwargs["kwargs"]
        )

    async def inner_callback(entity, attribute, old, new, kwargs):
        """
        Inner helper callback is called when entity changes occur.
        This schedules the actual callback to run after the given debounce delay.
        :param entity: the entity id
        :param attribute: the attribute that changed
        :param old: the old state
        :param new: the new state
        :param kwargs: additional arguments
        """
        nonlocal last_called_time
        now = util_common.now_in_berlin()
        if throttle_delay.total_seconds() > 0 and last_called_time is not None:
            time_since_last_call = now - last_called_time
            if time_since_last_call < throttle_delay:
                # self.log(
                #     f"Throttling callback for {entity_id}, time_since_last_call: {time_since_last_call}, throttle_delay: {throttle_delay} (last called at {last_called_time}, now is {now})")
                return
        last_called_time = now

        if util_ad_timer.is_scheduled(controller=controller, name=timer_key):
            await util_ad_timer.cancel(
                controller=controller,
                name=timer_key
            )
        combined_args = {
            "entity_id": entity,
            "attribute": attribute,
            "old": old,
            "new": new,
            "kwargs": kwargs
        }
        new_in_excluded_states = new in debounce_delay_excluded_states
        if debounce_delay.total_seconds() < 1 or new_in_excluded_states:
            await _callback_wrapper(combined_args)
        else:
            await util_ad_timer.schedule(
                controller=controller,
                name=timer_key,
                callback=_callback_wrapper,
                delay=int(debounce_delay.total_seconds()),
                **combined_args
            )

    await controller.listen_event(callback, event="plugin_started")
    if isinstance(entity_id, list):
        for entity in entity_id:
            await _listen_state_and_call_immediately_single(controller, inner_callback, entity, **kwargs)
        # run immediately
        await callback(None, None, None, None, kwargs)
    else:
        await _listen_state_and_call_immediately_single(controller, inner_callback, entity_id, **kwargs)
        # run immediately
        await callback(entity_id, None, None, await get_optional_state_or_default(controller=controller, entity_id=entity_id, **kwargs),
                       kwargs)


async def _listen_state_and_call_immediately_single(controller: ADAPI, callback, entity_id: str, **kwargs: Any):
    try:
        # await callback(entity_id, None, None, await self.get_state_or_default(entity_id=entity_id, **kwargs), kwargs)
        await controller.listen_state(callback, entity_id=entity_id, **kwargs)
    except Exception as e:
        controller.log(f"Error in listen_state_and_call_immediately_single: {e}", level="ERROR")


async def get_optional_state_or_default(controller: ADAPI, entity_id: str, default_states=None, default=None, **kwargs) -> Optional[Any]:
    """
    Gets the state of an entity.
    If the state is in default_states, the default value will be returned instead.

    :param controller: the appdaemon controller to use to get the state
    :param entity_id: the entity id to get the state for
    :param default_states: list of states that should be considered as "default", defaults to [STATE_UNAVAILABLE, STATE_UNKNOWN]
    :param default: the default value to return if the state is in default_states
    :param kwargs: additional arguments to pass to get_state
    :return: the state of the entity, or the default value if the state is in default_states
    """
    if default_states is None:
        default_states = [STATE_UNAVAILABLE, STATE_UNKNOWN]

    state = await controller.get_state(entity_id=entity_id, **kwargs)
    if state in default_states:
        return default
    else:
        return state


async def get_required_state_or_default(controller: ADAPI, entity_id: str, default: Any, default_states=None, **kwargs) -> Any:
    """
    Like get_optional_state_or_default, but returns the default if the state is None in addition to the default_states.
    """
    state = await get_optional_state_or_default(controller=controller, entity_id=entity_id, default_states=default_states, default=default, **kwargs)
    if state is None:
        return default
    else:
        return state
