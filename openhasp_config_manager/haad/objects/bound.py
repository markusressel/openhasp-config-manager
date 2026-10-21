from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from haad.hass.entity import HAEntity
from haad.triggers.resolver import TriggerInput


@dataclass(frozen=True)
class Bound[T]:
    """
    A property value that follows another entity (or any haad trigger), e.g.
    `border_width=Bound(co2_sensor, lambda x: 3 if x is not None and float(x) > 1000 else 0)`.

    It can be used for any property, as a leaf kwarg or in `add_*(props={...})`, for owned and external objects alike.
    Binding the object registers a reaction to `trigger` (applied immediately) and a `StateUpdater` entry, so every sync
    (e.g. after the plate reconnected) restores the value. Bound properties are not part of the pushed JSONL.
    """

    # the entity (HAEntity or entity id) to follow, or any haad trigger
    trigger: HAEntity | str | TriggerInput
    # converts the value (the entity state, or the result of get_state) into the property value. The entity state is None
    # while the entity is unknown or unavailable. Default: the value as it is.
    convert: Optional[Callable[[Any], T]] = None
    # the source of the value instead of the entity state; required for triggers that are not an entity
    get_state: Optional[Callable[[], Awaitable[Any]]] = None

    def __post_init__(self):
        if self.entity_id is None and self.get_state is None:
            raise ValueError(f"Bound on {self.trigger!r} needs get_state: only entity triggers have a state to convert")

    @property
    def entity_id(self) -> Optional[str]:
        """The id of the entity this value follows, None for other triggers."""
        if isinstance(self.trigger, str):
            return self.trigger
        if isinstance(self.trigger, HAEntity):
            return self.trigger.entity_id
        return None
