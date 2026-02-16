import copy
from dataclasses import dataclass, field
from typing import List, OrderedDict, Dict, Optional

from openhasp_config_manager.openhasp_client.model.device import Device


@dataclass
class PlateData:
    """Represents the actual content of a plate (pages and objects)."""

    jsonl_component_objects: OrderedDict[str, List[Dict]] = field(default_factory=OrderedDict)


class PlateSession:
    """
    Manages the lifecycle of a device's configuration during an app session.
    Holds the 'Snapshot' (disk) and 'Working' (UI) states.
    """

    def __init__(self, device: Device):
        self.device = device
        # The 'Source of Truth' as it exists on disk
        self._disk_snapshot: Optional[PlateData] = None
        # The current 'Draft' state modified by the UI
        self._working_draft: PlateData = PlateData()

        # Track if the UI has modified the draft
        self.is_dirty: bool = False

    def load_from_disk(self, data: OrderedDict[str, List[Dict]]):
        """Initializes both snapshot and draft from disk data."""
        self._disk_snapshot = PlateData(jsonl_component_objects=copy.deepcopy(data))
        self._working_draft = PlateData(jsonl_component_objects=copy.deepcopy(data))
        self.is_dirty = False

    @property
    def working_objects(self) -> OrderedDict[str, List[Dict]]:
        return self._working_draft.jsonl_component_objects

    def reset_to_disk(self):
        """Discards all UI changes."""
        if self._disk_snapshot:
            self._working_draft = copy.deepcopy(self._disk_snapshot)
            self.is_dirty = False

    def commit_to_snapshot(self):
        """Call this when the user hits 'Save' to make the draft the new baseline."""
        self._disk_snapshot = copy.deepcopy(self._working_draft)
        self.is_dirty = False
