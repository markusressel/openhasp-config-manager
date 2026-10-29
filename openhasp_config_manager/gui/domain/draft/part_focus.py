"""Part mode of a view: the instance of a part whose objects a view of a draft edits (see `PartFocus`)."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openhasp_config_manager.gui.domain.draft.model import PartInstance
from openhasp_config_manager.gui.domain.draft.session import PlateSession


class PartFocus:
    """
    Part mode of one view of a draft (an editor, later a part tab): the objects of one instance of a part can be changed like
    the objects of a file, every instance of the part follows, and the other objects are read-only. The draft has no part mode
    itself, so two views of it can be in different modes at once: one edits the part, the other one the pages.

    The methods that depend on the mode are those of the draft (`PlateSession`) with the instance. The draft keeps the instance
    up to date: it moves when a save moves the lines of its `!include`, and after a reload it is the instance included at the
    same place, or None if there is none (part mode ended, see `instance`). The changes of the part stay in the draft when the
    focus is closed.
    """

    def __init__(self, session: PlateSession, instance: PartInstance):
        """:raises ValueError: if the instance is not in the draft, or the part is also a file of the draft"""
        session.check_part_instance(instance)
        self.session = session
        # kept up to date by the draft (see `PlateSession._continue_part_focuses`)
        self.instance: Optional[PartInstance] = instance
        session.add_part_focus(self)

    def close(self):
        """Part mode ends: the draft doesn't keep the instance up to date anymore."""
        self.session.remove_part_focus(self)
        self.instance = None

    @property
    def is_active(self) -> bool:
        """Whether part mode goes on: False after a reload of the draft that doesn't include the instance anymore."""
        return self.instance is not None

    @property
    def part(self) -> Path:
        """The part that is edited (as the origins of its included objects have it)."""
        return self._instance().part

    @property
    def component(self) -> str:
        """The key new objects go into (see `add_object`)."""
        return str(self.part)

    def objects(self) -> List[Dict]:
        """:return: the rendered objects of the instance, also those of the parts it includes (none if it has no objects anymore)"""
        return self.session.objects_of_instance(self._instance())

    def describe(self) -> Optional[str]:
        """:return: where the instance is included (see `PlateSession.describe_instance`), None if it has no objects anymore"""
        return self.session.describe_instance(self.instance) if self.objects() else None

    # --- what depends on the mode ---

    def is_selectable(self, obj: Dict) -> bool:
        return self.session.is_selectable(obj, self.instance)

    def read_only_reason(self, obj: Dict) -> Optional[str]:
        return self.session.read_only_reason(obj, self.instance)

    def check_value(self, obj: Dict, key: str, value: Any) -> Optional[str]:
        return self.session.check_value(obj, key, value, self.instance)

    def set_source_value(self, obj: Dict, key: str, value: Any):
        self.session.set_source_value(obj, key, value, self.instance)

    def remove_source_value(self, obj: Dict, key: str):
        self.session.remove_source_value(obj, key, self.instance)

    def use_pixel_position(self, obj: Dict):
        self.session.use_pixel_position(obj, self.instance)

    def add_object(self, component: str, source: Dict[str, Any]) -> Optional[Dict]:
        return self.session.add_object(component, source, self.instance)

    def duplicate_object(self, obj: Dict, offset: int = 10) -> Dict:
        return self.session.duplicate_object(obj, offset, self.instance)

    def paste_objects(
        self,
        component: str,
        sources: List[Dict[str, Any]],
        page: int,
        screen: Tuple[int, int],
        position: Optional[Tuple[int, int]] = None,
        offset: int = 0,
    ) -> List[Dict]:
        return self.session.paste_objects(component, sources, page, screen, position, offset, self.instance)

    def remove_object(self, obj: Dict):
        self.session.remove_object(obj, self.instance)

    def _instance(self) -> PartInstance:
        if self.instance is None:
            raise ValueError("Part mode has ended: the draft doesn't include the instance anymore")
        return self.instance
