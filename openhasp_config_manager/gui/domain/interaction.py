"""
What touching the objects of the preview changes, the way it happens on a plate. Qt-free.

`RuntimeState` is what the objects look like after touches (their `val`, which one is pressed, ...). It lives next to the draft and
never changes it: the draft (`PlateSession`) is what the files say, the runtime state is what the plate would show after the
touches. `Indev` is the touch input of LVGL (`lv_indev.c`): which object a finger presses, when it loses the press, what a release does.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol, Set, Tuple

# the page and id of an object, the identity of an object on the plate
Key = Tuple[Optional[int], Optional[int]]
# a point of the plate
Point = Tuple[float, float]

# the input device of the plate (`lv_conf_v7.h`): how long a finger has to rest on an object for a long press, how often it repeats
LONG_PRESS_TIME = 0.4
LONG_PRESS_REPEAT_TIME = 0.2
# how far a finger has to move before an object that can be dragged starts to (`LV_INDEV_DEF_DRAG_LIMIT`)
DRAG_LIMIT = 10

# the types of objects that don't react to touches unless they say `click: true` (LVGL: `lv_obj_set_click(obj, false)` on creation)
_NOT_CLICKABLE = ("label", "img", "line", "bar", "qrcode")


def object_key(obj: Mapping) -> Key:
    return obj.get("page"), obj.get("id")


def is_true(value, default: bool) -> bool:
    """:return: a boolean property of an object (openHASP accepts true/false, 1/0 and their string forms)"""
    if value is None:
        return default
    return str(value).lower() not in ("false", "0", "")


def is_clickable(obj: Mapping) -> bool:
    """
    :return: whether a touch on an object reaches it: it is enabled, not hidden, and clickable (`click`, by default only labels, images, lines,
        bars and QR codes are not). Otherwise the touch goes to what is below it, like in `lv_indev_search_obj`.
    """
    if is_true(obj.get("hidden"), False) or not is_true(obj.get("enabled"), True):
        return False
    return is_true(obj.get("click"), obj.get("obj") not in _NOT_CLICKABLE)


class RuntimeState:
    """
    The state of the objects of a preview that touches changed, by object (`Key`).

    A changed property (`val`, `color`, ...) is remembered with the value the draft had when it was changed: when the draft changes
    that property afterwards (e.g. a new `val` from the property editor), the draft wins, like a plate that receives a new `val`.
    Names that start with `_` are not properties of the draft (e.g. the checked buttons of a button matrix) and stay.
    """

    def __init__(self):
        # object -> property -> (value, what the draft said when it was set)
        self._values: Dict[Key, Dict[str, Tuple[Any, Any]]] = {}
        # the object (and its button, row or tab, if it has them) a finger is pressing
        self.pressed: Optional[Key] = None
        self.pressed_part: Optional[int] = None
        # the dropdown whose list is open, and the row of it that is pressed
        self.open_dropdown: Optional[Key] = None
        self.pressed_row: Optional[int] = None
        # message boxes that were closed
        self.closed: Set[Key] = set()

    def clear(self):
        self.__init__()

    @property
    def is_empty(self) -> bool:
        return not self._values and self.pressed is None and self.open_dropdown is None and not self.closed

    def set(self, key: Key, name: str, value: Any, draft: Mapping):
        """Show `value` for a property of an object, until the draft changes the property."""
        self._values.setdefault(key, {})[name] = (value, None if name.startswith("_") else draft.get(name))

    def get(self, key: Key, name: str, draft: Mapping, default: Any = None) -> Any:
        """:return: the value of a property after the touches, the draft's if they didn't change it"""
        return self.effective(key, draft).get(name, default)

    def effective(self, key: Key, draft: Mapping) -> Mapping:
        """:return: the properties of an object as they are after the touches (`draft` itself if they changed nothing)"""
        changed = self._values.get(key)
        if not changed:
            return draft
        for name in [name for name, (_value, base) in changed.items() if not name.startswith("_") and draft.get(name) != base]:
            del changed[name]
        if not changed:
            del self._values[key]
            return draft
        return {**draft, **{name: value for name, (value, _base) in changed.items()}}

    def is_pressed(self, key: Key) -> bool:
        return self.pressed is not None and self.pressed == key

    def is_closed(self, key: Key) -> bool:
        return key in self.closed


class Target(Protocol):
    """What the input device needs to know of an object that can be touched (the items of the preview are these)."""

    @property
    def keeps_press(self) -> bool:
        """Whether a finger that leaves the object still presses it (`LV_PROTECT_PRESS_LOST`, or while it is dragged)."""

    def on_time(self, now: float):
        """Time passes while the finger is down on the object: before every press event, and between them (e.g. a finger that rests)."""

    def on_press(self, point: Point): ...

    def on_pressing(self, point: Point):
        """The finger is down on the object (called for every move, and for the press itself after `on_press`)."""

    def on_release(self, point: Point, short_click: bool):
        """:param short_click: the finger was not down for a long press, and the object was not dragged"""

    def on_press_lost(self): ...

    def on_long_press(self): ...

    def on_long_press_repeat(self): ...


@dataclass
class _Press:
    started: float
    long_sent: bool = False
    repeated: float = 0.0


class Indev:
    """
    The touch input of the plate, like `indev_proc_press` and `indev_proc_release` of LVGL: a finger presses the topmost object under it. When
    it moves onto another object (or onto none) the first loses the press (unless it keeps it, see `Target.keeps_press`) and the other one
    is pressed. Releasing sends the release to the pressed object.
    """

    def __init__(self, search):
        """:param search: `search(point)` returns the object a finger at a point of the plate presses (the topmost that is clickable)"""
        self._search = search
        self.active: Optional[Target] = None
        self._press: Optional[_Press] = None

    @property
    def is_pressing(self) -> bool:
        return self._press is not None

    def press(self, point: Point, now: Optional[float] = None):
        """The finger touches the plate, or moves while it does."""
        now = time.monotonic() if now is None else now
        if self._press is None:
            self._press = _Press(started=now)
        active = self.active
        if active is None or not active.keeps_press:
            found = self._search(point)
            if found is not active:
                if active is not None:
                    active.on_press_lost()
                self.active = found
                self._press = _Press(started=now)
                if found is not None:
                    found.on_time(now)
                    found.on_press(point)
        if self.active is not None:
            self.active.on_time(now)
            self.active.on_pressing(point)

    def release(self, point: Point):
        """The finger leaves the plate."""
        active, press = self.active, self._press
        self.active, self._press = None, None
        if active is not None and press is not None:
            active.on_release(point, short_click=not press.long_sent)

    def forget(self):
        """Forget the finger without telling the pressed object (it is gone, e.g. the page was reloaded)."""
        self.active, self._press = None, None

    def cancel(self):
        """Forget the finger, e.g. because the preview is not interactive anymore: the pressed object loses the press."""
        active = self.active
        self.active, self._press = None, None
        if active is not None:
            active.on_press_lost()

    def tick(self, now: float):
        """Time passes: a finger that rests on an object long enough long-presses it, and keeps doing so."""
        press, active = self._press, self.active
        if press is None or active is None:
            return
        active.on_time(now)
        if not press.long_sent:
            if now - press.started > LONG_PRESS_TIME:
                press.long_sent = True
                press.repeated = now
                active.on_long_press()
        elif now - press.repeated > LONG_PRESS_REPEAT_TIME:
            press.repeated = now
            active.on_long_press_repeat()
