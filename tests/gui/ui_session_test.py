from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest

from openhasp_config_manager.gui.domain.ui_session import DeviceSession, UiSession, from_data, to_data
from tests import TestBase


@dataclass
class _Zoom:
    level: float = 1.0


@dataclass
class _Extended:
    """A session that got new fields after it was stored."""

    name: Optional[str] = None
    count: int = 0
    pages: List[int] = field(default_factory=list)
    zooms: Dict[str, _Zoom] = field(default_factory=dict)


class TestUiSession(TestBase):
    def test_a_session_survives_the_round_trip(self):
        # GIVEN
        session = UiSession(selected_device="plate")
        session.device("plate").target_file = "devices/plate/page.jsonl"
        session.device("other")

        # WHEN
        result = from_data(UiSession, to_data(session))

        # THEN
        assert result == session
        assert result.devices["other"] == DeviceSession()

    def test_missing_unknown_and_invalid_values_get_the_defaults(self):
        # WHEN
        result = from_data(
            _Extended,
            {"name": 5, "count": True, "pages": [1, "x"], "zooms": {"a": {"level": 2.5}, "b": "x"}, "removed": 1},
        )

        # THEN
        assert result == _Extended(zooms={"a": _Zoom(level=2.5)})

    @pytest.mark.parametrize("data", [None, [], "x"])
    def test_data_that_is_no_object_gives_a_new_session(self, data):
        assert from_data(UiSession, data) == UiSession()
